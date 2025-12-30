import os
import urllib.parse
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

# --- AUTO SETUP DO BANCO ---
def init_db():
    try:
        res = supabase.table('stores').select("id").eq('slug', 'default').execute()
        if not res.data:
            print("CRIANDO LOJA DEFAULT NO BANCO...")
            supabase.table('stores').upsert({
                "slug": "default",
                "name": "Venda Vapt Vupt",
                "whatsapp": "5511999999999",
                "admin_user": "admin",
                "admin_password": "vaptvupt123",
                "whatsapp_message": "Olá! Quero comprar estes itens: "
            }).execute()
    except Exception as e:
        print(f"Erro no init_db: {e}")

init_db()

def get_store():
    # Mock Store de Fallback para evitar erro 500 se o Supabase estiver offline
    fallback_store = {
        "id": "00000000-0000-0000-0000-000000000000",
        "name": "Minha Loja Vapt Vupt",
        "whatsapp": "5511999999999",
        "primary_color": "#3B82F6",
        "secondary_color": "#10B981",
        "logo_url": None,
        "whatsapp_message": "Olá!"
    }
    try:
        res = supabase.table('stores').select("*").eq('slug', 'default').execute()
        if res.data: return res.data[0]
        init_db()
        res = supabase.table('stores').select("*").eq('slug', 'default').execute()
        return res.data[0] if res.data else fallback_store
    except:
        return fallback_store

# --- HELPERS ---
def check_auth():
    return 'is_admin' in session

def generate_wa_link(phone, base_msg, cart_items=None, total=None):
    msg = base_msg
    if cart_items:
        msg += "\n\n📋 *MEU PEDIDO:*\n"
        for item in cart_items:
            msg += f"- {item['quantity']}x {item['name']}\n"
        if total:
            msg += f"\n💰 *TOTAL:* R$ {total:.2f}"

    encoded_msg = urllib.parse.quote(msg)
    return f"https://wa.me/{phone}?text={encoded_msg}"

# --- ROTAS PRINCIPAIS (VITRINE) ---

@app.route('/')
def index():
    store = get_store()
    query = request.args.get('q', '').strip()
    products = []

    try:
        if store and store.get('id') != "00000000-0000-0000-0000-000000000000":
            req = supabase.table('products').select("*").eq('store_id', store['id']).eq('is_active', True)
            if query:
                req = req.ilike('name', f'%{query}%')
            products_res = req.execute()
            products = products_res.data if products_res.data else []
    except Exception as e:
        print(f"Erro ao carregar vitrine: {e}")

    return render_template('store.html', store=store, products=products, query=query)

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
    if request.method == 'POST':
        # Concatenar endereço completo
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
            "whatsapp": request.form.get('whatsapp'),
            "address_full": address_details
        }

        cust_res = supabase.table('customers').upsert(customer_data, on_conflict="whatsapp").execute()
        customer_id = cust_res.data[0]['id']

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

                    # Deduzir estoque
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

# --- LOGIN E ADMIN ---

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        store = get_store()

        # Login Resiliente
        is_store_admin = store and store.get('admin_user') == username and store.get('admin_password') == password
        is_default_admin = (not store or not store.get('admin_user')) and username == 'admin' and password == 'vaptvupt123'

        if is_store_admin or is_default_admin:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        return render_template('login.html', error="Credenciais inválidas")

    return render_template('login.html')

@app.route('/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/vendedor')
def admin_dashboard():
    if not check_auth(): return redirect(url_for('admin_login'))

    store = get_store()
    orders = []
    products = []

    if store and store.get('id') != "00000000-0000-0000-0000-000000000000":
        try:
            orders_res = supabase.table('orders').select("*, customers(*)").eq('store_id', store['id']).order('created_at', desc=True).execute()
            orders = orders_res.data if orders_res.data else []

            products_res = supabase.table('products').select("*").eq('store_id', store['id']).order('created_at', desc=True).execute()
            products = products_res.data if products_res.data else []
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
        "admin_password": request.form.get('admin_password', 'vaptvupt123')
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
        "price": float(request.form.get('price')),
        "stock_quantity": int(request.form.get('stock_quantity', 99)),
        "image_url": request.form.get('image_url')
    }

    file = request.files.get('file')
    if file and file.filename:
        try:
            filename = f"prod_{uuid.uuid4()}.{file.filename.split('.')[-1]}"
            supabase.storage.from_('product-images').upload(filename, file.read())
            product_data["image_url"] = supabase.storage.from_('product-images').get_public_url(filename)
        except: pass

    supabase.table('products').insert(product_data).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/pedido/<order_id>/status', methods=['POST'])
def update_order_status(order_id):
    if not check_auth(): return redirect(url_for('admin_login'))
    new_status = request.form.get('status')
    supabase.table('orders').update({"status": new_status}).eq('id', order_id).execute()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
