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
            supabase.table('stores').upsert({
                "slug": "default",
                "name": "Venda Vapt Vupt",
                "whatsapp": "5511999999999",
                "admin_user": "admin",
                "admin_password": "admin",
                "whatsapp_message": "Olá! Quero comprar estes itens: "
            }).execute()
        else:
            # Garantir credenciais solicitadas se a loja padrão existir mas estiver com a antiga
            s = res.data[0]
            if s.get('admin_user') == 'admin' and s.get('admin_password') == 'vaptvupt123':
                 supabase.table('stores').update({"admin_password": "admin"}).eq('slug', 'default').execute()
    except: pass

init_db()

def get_store():
    fallback_store = {
        "id": "00000000-0000-0000-0000-000000000000",
        "name": "Minha Loja Vapt Vupt",
        "whatsapp": "5511999999999",
        "primary_color": "#10B981",
        "secondary_color": "#059669",
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

        # 1. Login Admin
        if (store and store.get('admin_user') == login_id and store.get('admin_password') == password) or \
           (not store and login_id == 'admin' and password == 'admin'):
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        # 2. Login Cliente
        try:
            c_res = supabase.table('customers').select("*").eq('email', login_id).eq('password', password).execute()
            if not c_res.data:
                c_res = supabase.table('customers').select("*").eq('whatsapp', login_id).eq('password', password).execute()
            if c_res.data:
                session['customer_id'] = c_res.data[0]['id']
                session['customer_name'] = c_res.data[0]['name']
                return redirect(url_for('customer_orders'))
        except: pass

        return render_template('login.html', error="Login ou senha incorretos")
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
            products = supabase.table('products').select("*").eq('store_id', store['id']).order('created_at', desc=True).execute().data
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
        "store_id": store['id'], "name": request.form.get('name'), "description": request.form.get('description'),
        "price": float(request.form.get('price')), "stock_quantity": int(request.form.get('stock_quantity', 99)),
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
