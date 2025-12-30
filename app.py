import os
import urllib.parse
import requests
import re
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client
from pix_utils import PixGenerator
import uuid

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "prod_secret_vapt123")

# Configuração Supabase
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

# --- AUTO SETUP DO BANCO/SCHEMA ---
def init_db():
    try:
        # Garantir Store padrão
        res = supabase.table('stores').select("id").eq('slug', 'default').execute()
        if not res.data:
            supabase.table('stores').insert({
                "slug": "default",
                "name": "Venda Vapt Vupt",
                "whatsapp": "5511999999999",
                "admin_user": "admin",
                "admin_password": "admin"
            }).execute()

        # Sincronização de Colunas (Schema Evolution)
        rpc_cols = [
            {'t_name': 'products', 'c_name': 'external_url', 'c_type': 'TEXT'},
            {'t_name': 'products', 'c_name': 'is_active', 'c_type': 'BOOLEAN DEFAULT TRUE'},
            {'t_name': 'products', 'c_name': 'clicks_count', 'c_type': 'INTEGER DEFAULT 0'},
            {'t_name': 'stores', 'c_name': 'pix_key', 'c_type': 'TEXT'},
            {'t_name': 'stores', 'c_name': 'pix_name', 'c_type': 'TEXT'},
            {'t_name': 'stores', 'c_name': 'pix_city', 'c_type': 'TEXT'}
        ]
        for col in rpc_cols:
            try: supabase.rpc('add_column_if_not_exists', col).execute()
            except: pass

        # Forçar admin/admin
        try: supabase.table('stores').update({"admin_user": "admin", "admin_password": "admin"}).eq('slug', 'default').execute()
        except: pass
    except Exception as e:
        print(f"Erro init_db: {e}")

init_db()

# --- HELPERS ---
def get_store():
    fallback = {"id": str(uuid.uuid4()), "name": "Vapt Vupt", "whatsapp": "5511999999999", "primary_color": "#0EA5E9"}
    try:
        res = supabase.table('stores').select("*").eq('slug', 'default').execute()
        return res.data[0] if res.data else fallback
    except: return fallback

def check_auth(): return 'is_admin' in session

def generate_wa_link(phone, base_msg, cart_items=None, total=None):
    msg = base_msg
    if cart_items:
        msg += "\n\n📋 *MEU PEDIDO:*\n"
        for item in cart_items:
            msg += f"- {item['quantity']}x {item['name']}\n"
        if total: msg += f"\n💰 *TOTAL:* R$ {total:.2f}"
    return f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"

# --- ROTAS VITRINE ---
@app.route('/')
def index():
    store = get_store()
    query = request.args.get('q', '').strip()
    products = []
    try:
        req = supabase.table('products').select("*, product_images(*)").eq('store_id', store['id'])
        if query: req = req.ilike('name', f'%{query}%')
        products = req.order('created_at', desc=True).execute().data or []
    except Exception as e: app.logger.error(f"Erro Vitrine: {e}")

    try:
        return render_template('store.html', store=store, products=products, query=query)
    except Exception as e:
        app.logger.error(f"Erro Render: {e}")
        return render_template('error.html', error="Erro de exibição", store=store), 500

@app.route('/clique/<product_id>')
def track_click(product_id):
    try:
        # Incrementa contador de cliques de forma atômica se possível, ou via update simples
        p_res = supabase.table('products').select("external_url, clicks_count").eq('id', product_id).execute()
        if p_res.data:
            prod = p_res.data[0]
            current_clicks = prod.get('clicks_count') or 0
            supabase.table('products').update({"clicks_count": current_clicks + 1}).eq('id', product_id).execute()
            if prod.get('external_url'): return redirect(prod['external_url'])
    except: pass
    return redirect(url_for('index'))

@app.errorhandler(404)
def page_not_found(e): return render_template('error.html', error="Página não encontrada", store=get_store()), 404

@app.errorhandler(500)
def server_error(e):
    app.logger.error(f"500: {e}")
    return render_template('error.html', error="Erro interno", store=get_store()), 500

@app.route('/carrinho/adicionar', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    qty_requested = int(request.form.get('quantity', 1))

    try:
        p_res = supabase.table('products').select("name, stock_quantity").eq('id', product_id).execute()
        if p_res.data:
            product = p_res.data[0]
            stock = product.get('stock_quantity', 0)
            if stock < qty_requested:
                return jsonify({"status": "error", "message": f"Estoque insuficiente ({stock} disponíveis)"})
    except: pass

    if 'cart' not in session: session['cart'] = {}
    cart = session['cart']
    cart[product_id] = cart.get(product_id, 0) + qty_requested
    session['cart'] = cart

    return jsonify({"status": "success", "cart_count": sum(cart.values())})

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    store = get_store()
    cart = session.get('cart', {})
    if not cart and request.method == 'GET':
        return render_template('checkout.html', store=store, empty_cart=True)

    if request.method == 'POST':
        street = request.form.get('street', 'Não informado')
        number = request.form.get('number', 'S/N')
        complement = request.form.get('complement', '')
        neighborhood = request.form.get('neighborhood', '')
        city = request.form.get('city', '')
        state = request.form.get('state', '')
        cep = request.form.get('cep', '')

        address_details = f"{street}, {number}"
        if complement: address_details += f" - {complement}"
        address_details += f", {neighborhood}, {city} - {state} (CEP: {cep})"

        customer_data = {
            "name": request.form.get('name'),
            "email": request.form.get('email'),
            "whatsapp": request.form.get('whatsapp'),
            "address_full": address_details
        }

        cust_res = supabase.table('customers').upsert(customer_data, on_conflict="email").execute()
        if cust_res.data:
            customer_id = cust_res.data[0]['id']
            # Identifica automaticamente o cliente na sessão
            session['customer_id'] = customer_id
            session['customer_name'] = cust_res.data[0]['name']
        else:
            return render_template('checkout.html', error="Erro ao processar dados do cliente.", store=store)

        cart = session.get('cart', {})
        total = 0
        order_items_to_save = []
        cart_for_wa = []

        for pid, qty in cart.items():
            try:
                p_res = supabase.table('products').select("name, price, stock_quantity").eq('id', pid).execute()
                if p_res.data:
                    p = p_res.data[0]
                    price = float(p['price'])
                    total += price * qty
                    order_items_to_save.append({"product_id": pid, "quantity": qty, "unit_price": price})
                    cart_for_wa.append({"name": p['name'], "quantity": qty})

                    new_stock = (p.get('stock_quantity') or 0) - qty
                    supabase.table('products').update({"stock_quantity": new_stock}).eq('id', pid).execute()
            except: pass

        order_res = supabase.table('orders').insert({
            "store_id": store['id'],
            "customer_id": customer_id,
            "subtotal": total,
            "total": total,
            "status": "pending_payment",
            "delivery_address": address_details
        }).execute()

        order_id = order_res.data[0]['id']
        for item in order_items_to_save:
            item['order_id'] = order_id
            supabase.table('order_items').insert(item).execute()

        wa_link = generate_wa_link(store['whatsapp'], store.get('whatsapp_message', 'Novo pedido!'), cart_for_wa, total)
        session.pop('cart', None)
        return redirect(url_for('order_confirmation', order_id=order_id, wa_link=wa_link))

    return render_template('checkout.html', store=store)

@app.route('/confirmacao/<order_id>')
def order_confirmation(order_id):
    order_res = supabase.table('orders').select("*, stores(*)").eq('id', order_id).execute()
    order = order_res.data[0]
    wa_link = request.args.get('wa_link')
    pix_chave = order['stores'].get('pix_key') or "pendente@pix.com"
    pix_nome = order['stores'].get('pix_name') or order['stores'].get('name', 'VAPT VUPT')
    pix_cidade = order['stores'].get('pix_city') or "SAO PAULO"
    pix = PixGenerator(pix_chave, pix_nome, pix_cidade, float(order['total']))
    qr_code, payload = pix.generate_qr_base64()
    return render_template('confirmation.html', order=order, qr_code=qr_code, payload=payload, wa_link=wa_link)

# --- CADASTRO E LOGIN ---

@app.route('/cadastro', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        street = request.form.get('street')
        number = request.form.get('number')
        complement = request.form.get('complement')
        neighborhood = request.form.get('neighborhood')
        city = request.form.get('city')
        state = request.form.get('state')
        cep = request.form.get('cep')
        address_details = f"{street}, {number}"
        if complement: address_details += f" - {complement}"
        address_details += f", {neighborhood}, {city} - {state} (CEP: {cep})"

        customer_data = {
            "name": request.form.get('name'),
            "email": request.form.get('email'),
            "whatsapp": request.form.get('whatsapp'),
            "password": request.form.get('password'),
            "address_full": address_details
        }
        try:
            res = supabase.table('customers').insert(customer_data).execute()
            if res.data:
                session['customer_id'] = res.data[0]['id']
                session['customer_name'] = res.data[0]['name']
                if session.get('cart'): return redirect(url_for('checkout'))
                return redirect(url_for('customer_orders'))
        except Exception as e:
            return render_template('register.html', error=f"Erro ao cadastrar: {e}")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        login_id = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        store = get_store()

        # 1. Login Admin (Prioridade para admin/admin como solicitado)
        try:
            # 1. Login Admin
            is_god_mode = (login_id == 'admin' and password == 'admin')
            is_store_admin = store and store.get('admin_user') == login_id and store.get('admin_password') == password

            if is_god_mode or is_store_admin:
                session['is_admin'] = True
                return redirect(url_for('admin_dashboard'))

            # 2. Login Cliente
            c_res = supabase.table('customers').select("*").eq('email', login_id).eq('password', password).execute()
            if not c_res.data:
                c_res = supabase.table('customers').select("*").eq('whatsapp', login_id).eq('password', password).execute()

            if c_res.data:
                session['customer_id'] = c_res.data[0]['id']
                session['customer_name'] = c_res.data[0]['name']
                if session.get('cart'): return redirect(url_for('checkout'))
                return redirect(url_for('customer_orders'))

            return render_template('login.html', error="Login ou senha incorretos")
        except Exception as e:
            app.logger.error(f"Erro Login: {e}")
            return render_template('login.html', error=f"Erro interno no login: {str(e)}")
    return render_template('login.html')

@app.route('/meus-pedidos')
def customer_orders():
    if 'customer_id' not in session: return redirect(url_for('admin_login'))
    orders = []
    try:
        orders = supabase.table('orders').select("*, stores(*)").eq('customer_id', session['customer_id']).order('created_at', desc=True).execute().data
    except: pass
    return render_template('customer_orders.html', orders=orders)

@app.route('/logout')
def admin_logout():
    session.pop('is_admin', None)
    session.pop('customer_id', None)
    session.pop('customer_name', None)
    return redirect(url_for('index'))

@app.route('/vendedor')
def admin_dashboard():
    if not check_auth(): return redirect(url_for('admin_login'))
    store = get_store()
    orders, products = [], []
    if store and store.get('id') != "00000000-0000-0000-0000-000000000000":
        try:
            orders = supabase.table('orders').select("*, customers(*)").eq('store_id', store['id']).order('created_at', desc=True).execute().data
            products = supabase.table('products').select("*, product_images(*)").eq('store_id', store['id']).order('created_at', desc=True).execute().data
        except: pass
    return render_template('admin.html', store=store, orders=orders, products=products)

@app.route('/vendedor/configuracoes', methods=['POST'])
def update_settings():
    if not check_auth(): return redirect(url_for('admin_login'))
    store_data = {
        "name": request.form.get('name'),
        "whatsapp": request.form.get('whatsapp'),
        "whatsapp_message": request.form.get('whatsapp_message'),
        "primary_color": request.form.get('primary_color'),
        "secondary_color": request.form.get('secondary_color'),
        "logo_url": request.form.get('logo_url'),
        "pix_key": request.form.get('pix_key'),
        "pix_name": request.form.get('pix_name'),
        "pix_city": request.form.get('pix_city'),
        "admin_user": request.form.get('admin_user', 'admin'),
        "admin_password": request.form.get('admin_password', 'admin')
    }
    file = request.files.get('file')
    if file and file.filename:
        try:
            filename = f"logo_{uuid.uuid4()}.{file.filename.split('.')[-1]}"
            supabase.storage.from_('product-images').upload(filename, file.read())
            store_data["logo_url"] = supabase.storage.from_('product-images').get_public_url(filename)
        except: pass
    supabase.table('stores').upsert(dict(store_data, slug="default")).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/produto/novo', methods=['POST'])
def admin_add_product():
    if not check_auth(): return redirect(url_for('admin_login'))
    store = get_store()
    product_data = {
        "store_id": store['id'],
        "name": request.form.get('name'),
        "description": request.form.get('description'),
        "price": float(request.form.get('price') or 0),
        "stock_quantity": int(request.form.get('stock_quantity', 1)),
        "image_url": request.form.get('image_url'),
        "external_url": request.form.get('external_url')
    }
    file = request.files.get('file')
    if file and file.filename:
        try:
            filename = f"prod_{uuid.uuid4()}.{file.filename.split('.')[-1]}"
            supabase.storage.from_('product-images').upload(filename, file.read())
            product_data["image_url"] = supabase.storage.from_('product-images').get_public_url(filename)
        except: pass
    p_res = supabase.table('products').insert(product_data).execute()

    if p_res.data:
        new_prod_id = p_res.data[0]['id']
        extra_images_json = request.form.get('extra_images')

        if extra_images_json:
            try:
                import json
                images_list = json.loads(extra_images_json)
                if isinstance(images_list, list):
                    img_rows = [{"product_id": new_prod_id, "image_url": img, "display_order": i} for i, img in enumerate(images_list)]
                    if img_rows: supabase.table('product_images').insert(img_rows).execute()
            except: pass

    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/produto/<product_id>/delete', methods=['POST'])
def admin_delete_product(product_id):
    if not check_auth(): return redirect(url_for('admin_login'))
    supabase.table('products').delete().eq('id', product_id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/pedido/<order_id>/status', methods=['POST'])
def update_order_status(order_id):
    if not check_auth(): return redirect(url_for('admin_login'))
    new_status = request.form.get('status')
    supabase.table('orders').update({"status": new_status}).eq('id', order_id).execute()
    return redirect(url_for('admin_dashboard'))

# --- NOVAS FUNCIONALIDADES AVANÇADAS ---

@app.route('/vendedor/fetch-metadata')
def fetch_metadata():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    url_to_fetch = request.args.get('url')
    if not url_to_fetch: return jsonify({"error": "no url"}), 400

    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url_to_fetch, headers=headers, timeout=15)
        html = response.text

        data = {
            "title": "",
            "description": "",
            "price": 0,
            "images": [],
            "video": "",
            "stock": 1
        }

        # 1. Tentar extrair via JSON-LD (Dados Estruturados - Melhor Precisão)
        try:
            json_ld_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            for json_str in json_ld_matches:
                try:
                    import json
                    ld = json.loads(json_str)
                    if isinstance(ld, dict):
                        # Se for Product ou conter Product
                        target = ld if ld.get('@type') == 'Product' else None
                        if not target and '@graph' in ld:
                            for item in ld['@graph']:
                                if item.get('@type') == 'Product':
                                    target = item
                                    break

                        if target:
                            data["title"] = target.get('name', data["title"])
                            data["description"] = target.get('description', data["description"])

                            # Imagens (pode ser string ou lista)
                            imgs = target.get('image')
                            if isinstance(imgs, str): data["images"].append(imgs)
                            elif isinstance(imgs, list): data["images"].extend(imgs)

                            # Ofertas (Preço)
                            offers = target.get('offers')
                            if isinstance(offers, dict):
                                data["price"] = float(offers.get('price', 0))
                            elif isinstance(offers, list) and len(offers) > 0:
                                data["price"] = float(offers[0].get('price', 0))

                            break # Encontrou produto, para
                except: pass
        except: pass

        # 2. Fallbacks via Meta Tags e Regex (se JSON-LD falhar ou estiver incompleto)

        if not data["title"]:
            match = re.search(r'property=["\']og:title["\'] content=["\'](.*?)["\']', html) or re.search(r'<title>(.*?)</title>', html)
            if match: data["title"] = match.group(1)

        if not data["description"]:
             match = re.search(r'property=["\']og:description["\'] content=["\'](.*?)["\']', html)
             if match: data["description"] = match.group(1)

        if not data["price"]:
            # Tentar meta tags de preço
            match = re.search(r'property=["\']product:price:amount["\'] content=["\'](.*?)["\']', html) or \
                    re.search(r'property=["\']og:price:amount["\'] content=["\'](.*?)["\']', html)
            if match:
                try: data["price"] = float(match.group(1))
                except: pass

            # Tentar regex no corpo (R$ XX,XX)
            if not data["price"]:
                prices = re.findall(r'R\$\s?(\d+[.,]?\d*)', html)
                if prices:
                    try: data["price"] = float(prices[0].replace('.', '').replace(',', '.'))
                    except: pass

        # Buscar Imagens adicionais (OpenGraph, Twitter, Links diretos)
        if not data["images"]:
            og_img = re.search(r'property=["\']og:image["\'] content=["\'](.*?)["\']', html)
            if og_img: data["images"].append(og_img.group(1))

            # Buscar todas as imagens jpg/png grandes (heurística simples) que não sejam ícones
            matches = re.findall(r'(https?://[^"\s]+\.(?:jpg|jpeg|png|webp))', html, re.IGNORECASE)
            # Filtrar e desduplicar (limite de 5 para não poluir)
            data["images"].extend([m for m in matches if 'icon' not in m and 'logo' not in m][:5])

        # Deduplicar imagens
        data["images"] = list(dict.fromkeys(data["images"]))

        # Video
        if not data["video"]:
            vid = re.search(r'property=["\']og:video["\'] content=["\'](.*?)["\']', html)
            if vid: data["video"] = vid.group(1)

        return jsonify({
            "title": data["title"],
            "description": data["description"],
            "image": data["images"][0] if data["images"] else "",
            "images": data["images"],
            "video": data["video"],
            "price": data["price"],
            "stock": 1
        })

    except Exception as e:
        app.logger.error(f"Erro Scraper: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/vendedor/produto/<product_id>/imagem/nova', methods=['POST'])
def admin_add_product_image(product_id):
    if not check_auth(): return redirect(url_for('admin_login'))
    file = request.files.get('file')
    if file and file.filename:
        try:
            filename = f"prod_gal_{uuid.uuid4()}.{file.filename.split('.')[-1]}"
            supabase.storage.from_('product-images').upload(filename, file.read())
            img_url = supabase.storage.from_('product-images').get_public_url(filename)
            supabase.table('product_images').insert({"product_id": product_id, "image_url": img_url}).execute()
        except: pass
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/produto/imagem/<image_id>/delete', methods=['POST'])
def admin_delete_product_image(image_id):
    if not check_auth(): return redirect(url_for('admin_login'))
    supabase.table('product_images').delete().eq('id', image_id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/clientes')
def admin_customers():
    if not check_auth(): return redirect(url_for('admin_login'))
    customers = []
    try:
        customers = supabase.table('customers').select("*").order('name').execute().data
    except: pass
    return render_template('admin_customers.html', customers=customers)

@app.route('/vendedor/cliente/reset-senha', methods=['POST'])
def admin_reset_customer_password():
    if not check_auth(): return redirect(url_for('admin_login'))
    cid = request.form.get('customer_id')
    new_pass = request.form.get('new_password')
    if cid and new_pass:
        supabase.table('customers').update({"password": new_pass}).eq('id', cid).execute()
    return redirect(url_for('admin_customers'))

if __name__ == '__main__':
    app.run(debug=True)
