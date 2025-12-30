import os
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
        # Verifica se já existe a loja principal
        res = supabase.table('stores').select("id").eq('slug', 'default').execute()
        if not res.data:
            print("Executando setup inicial do banco de dados...")
            supabase.table('stores').upsert({
                "slug": "default",
                "name": "Venda Vapt Vupt",
                "whatsapp": "5511999999999",
                "admin_user": "admin",
                "admin_password": "vaptvupt123"
            }).execute()
    except Exception as e:
        print(f"Nota: Certifique-se de rodar o SQL no painel do Supabase uma vez. Erro: {e}")

init_db() # Chamado no boot para garantir que a loja principal exista

def get_store():
    try:
        res = supabase.table('stores').select("*").eq('slug', 'default').execute()
        return res.data[0] if res.data else None
    except:
        return None

# --- HELPERS ---
def check_auth():
    return 'is_admin' in session

# --- ROTAS PRINCIPAIS (VITRINE) ---

@app.route('/')
def index():
    store = get_store()
    if not store: return "Sistema em configuração. Aguarde...", 503

    products = []
    try:
        products_res = supabase.table('products').select("*").eq('store_id', store['id']).eq('is_active', True).execute()
        products = products_res.data
    except: pass

    return render_template('store.html', store=store, products=products)

@app.route('/carrinho/adicionar', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    if 'cart' not in session: session['cart'] = {}

    cart = session['cart']
    cart[product_id] = cart.get(product_id, 0) + 1
    session['cart'] = cart

    return jsonify({"status": "success", "cart_count": sum(cart.values())})

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    store = get_store()
    if request.method == 'POST':
        # Criar Pedido
        customer_data = {
            "name": request.form.get('name'),
            "whatsapp": request.form.get('whatsapp'),
            "address_full": request.form.get('address')
        }

        # Upsert Customer
        cust_res = supabase.table('customers').upsert(customer_data, on_conflict="whatsapp").execute()
        customer_id = cust_res.data[0]['id']

        # Calcular Total
        cart = session.get('cart', {})
        total = 0
        order_items = []

        for pid, qty in cart.items():
            p_res = supabase.table('products').select("price").eq('id', pid).execute()
            price = float(p_res.data[0]['price'])
            total += price * qty
            order_items.append({"product_id": pid, "quantity": qty, "unit_price": price})

        order_res = supabase.table('orders').insert({
            "store_id": store['id'],
            "customer_id": customer_id,
            "subtotal": total,
            "total": total,
            "status": "pending_payment",
            "delivery_address": customer_data['address_full']
        }).execute()

        order_id = order_res.data[0]['id']

        # Inserir Itens
        for item in order_items:
            item['order_id'] = order_id
            supabase.table('order_items').insert(item).execute()

        session.pop('cart', None)
        return redirect(url_for('order_confirmation', order_id=order_id))

    return render_template('checkout.html', store=store)

@app.route('/confirmacao/<order_id>')
def order_confirmation(order_id):
    order_res = supabase.table('orders').select("*, stores(*)").eq('id', order_id).execute()
    order = order_res.data[0]

    pix_chave = order['stores'].get('pix_key') or "pendente@pix.com"
    pix_nome = order['stores'].get('pix_name') or order['stores'].get('name', 'VAPT VUPT')
    pix_cidade = order['stores'].get('pix_city') or "SAO PAULO"

    pix = PixGenerator(pix_chave, pix_nome, pix_cidade, float(order['total']))
    qr_code, payload = pix.generate_qr_base64()

    return render_template('confirmation.html', order=order, qr_code=qr_code, payload=payload)

# --- LOGIN E SEGURANÇA ---

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        store = get_store()

        # 1. Login via Banco
        if store:
            db_user = (store.get('admin_user') or 'admin').strip()
            db_pass = (store.get('admin_password') or 'vaptvupt123').strip()
            if username == db_user and password == db_pass:
                session['is_admin'] = True
                return redirect(url_for('admin_dashboard'))

        # 2. Fallback de Emergência
        if (not store or not store.get('admin_user')) and username == 'admin' and password == 'vaptvupt123':
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        return render_template('login.html', error="Usuário ou Senha incorretos")

    return render_template('login.html')

@app.route('/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

# --- PAINEL ADMINISTRATIVO (VENDEDOR) ---

@app.route('/vendedor')
def admin_dashboard():
    if not check_auth(): return redirect(url_for('admin_login'))

    store = None
    orders = []
    products = []

    try:
        store = get_store()
        if store and 'id' in store:
            try:
                orders_res = supabase.table('orders').select("*, customers(*)").eq('store_id', store['id']).order('created_at', desc=True).execute()
                orders = orders_res.data if orders_res.data else []
            except: pass

            try:
                products_res = supabase.table('products').select("*").eq('store_id', store['id']).execute()
                products = products_res.data if products_res.data else []
            except: pass
    except: pass

    return render_template('admin.html', store=store, orders=orders, products=products)

@app.route('/vendedor/configuracoes', methods=['POST'])
def update_settings():
    if not check_auth(): return redirect(url_for('admin_login'))

    store_data = {
        "name": request.form.get('name'),
        "whatsapp": request.form.get('whatsapp'),
        "primary_color": request.form.get('primary_color'),
        "secondary_color": request.form.get('secondary_color'),
        "logo_url": request.form.get('logo_url'),
        "pix_key": request.form.get('pix_key'),
        "pix_name": request.form.get('pix_name'),
        "pix_city": request.form.get('pix_city'),
        "admin_user": request.form.get('admin_user', 'admin'),
        "admin_password": request.form.get('admin_password', 'vaptvupt123'),
        "address_street": request.form.get('address_street'),
        "address_number": request.form.get('address_number'),
        "address_city": request.form.get('address_city'),
        "address_state": request.form.get('address_state')
    }

    file = request.files.get('file')
    if file and file.filename:
        try:
            file_ext = file.filename.split('.')[-1]
            filename = f"logo_{uuid.uuid4()}.{file_ext}"
            supabase.storage.from_('product-images').upload(filename, file.read())
            store_data["logo_url"] = supabase.storage.from_('product-images').get_public_url(filename)
        except: pass

    try:
        supabase.table('stores').upsert(dict(store_data, slug="default")).execute()
    except Exception as e:
        print(f"Erro ao salvar config: {e}")

    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/produto/novo', methods=['POST'])
def admin_add_product():
    if not check_auth(): return redirect(url_for('admin_login'))
    store = get_store()
    if not store: return redirect(url_for('admin_dashboard'))

    product_data = {
        "store_id": store['id'],
        "name": request.form.get('name'),
        "description": request.form.get('description'),
        "price": float(request.form.get('price')),
        "image_url": request.form.get('image_url')
    }

    file = request.files.get('file')
    if file and file.filename != '':
        try:
            ext = file.filename.split('.')[-1]
            filename = f"{uuid.uuid4()}.{ext}"
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
