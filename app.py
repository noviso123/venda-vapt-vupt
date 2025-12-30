import os
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client
from pix_utils import PixGenerator
import uuid

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")

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
            with open('setup_db.sql', 'r', encoding='utf-8') as f:
                sql = f.read()
            # Como não podemos rodar SQL arbitrário via SDK Rest,
            # assumimos que tabelas existem ou usamos RPC se configurado.
            # Por agora, garantimos que seeds rodam se tabelas existirem.
            supabase.table('stores').upsert({"slug": "default", "name": "Venda Vapt Vupt", "whatsapp": "5511999999999"}).execute()
    except Exception as e:
        print(f"Nota: Certifique-se de rodar o SQL no painel do Supabase uma vez. Erro: {e}")

# init_db() # Chamado no boot se necessário

def get_store():
    # Em Single-Tenant, sempre pegamos a única loja ativada
    res = supabase.table('stores').select("*").eq('slug', 'default').execute()
    return res.data[0] if res.data else None

# --- HELPERS ---
def check_auth():
    if 'is_admin' not in session:
        return False
    return True

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    store = get_store()
    if not store: return "Sistema em configuração. Aguarde...", 503

    # Buscar produtos da loja
    products_res = supabase.table('products').select("*").eq('store_id', store['id']).eq('is_active', True).execute()
    products = products_res.data

    return render_template('store.html', store=store, products=products)

@app.route('/adicionar_carrinho', methods=['POST'])
def add_to_cart():
    product_id = request.form.get('product_id')
    store_id = request.form.get('store_id')

    if 'cart' not in session:
        session['cart'] = {}

    cart = session['cart']
    cart[product_id] = cart.get(product_id, 0) + 1
    session['cart'] = cart

    return jsonify({"success": True, "cart_count": sum(cart.values())})

@app.route('/checkout')
def checkout():
    store = get_store()
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('index'))

    # Buscar detalhes dos itens no carrinho
    product_ids = list(cart.keys())
    products_res = supabase.table('products').select("*").in_('id', product_ids).execute()
    products = products_res.data

    total = 0
    items = []
    for p in products:
        qty = cart[p['id']]
        subtotal = float(p['price']) * qty
        total += subtotal
        items.append({
            "id": p['id'],
            "name": p['name'],
            "price": p['price'],
            "qty": qty,
            "subtotal": subtotal
        })

    return render_template('checkout.html', store=store, items=items, total=total)

@app.route('/finalizar_pedido', methods=['POST'])
def finalize_order():
    # 1. Pegar dados do cliente e entrega
    store_id = request.form.get('store_id')
    customer_whatsapp = request.form.get('whatsapp')
    customer_name = request.form.get('name')
    address = request.form.get('address')

    # 2. Upsert Cliente (Supabase)
    customer_data = {
        "whatsapp": customer_whatsapp,
        "name": customer_name,
        "address_full": address
    }
    customer_res = supabase.table('customers').upsert(customer_data, on_conflict='whatsapp').execute()
    customer = customer_res.data[0]

    # 3. Criar Pedido e Calcular Frete Real
    from uber_utils import UberDirect
    uber = UberDirect()

    # Endereço da loja (vire do banco ou .env)
    store_res = supabase.table('stores').select("*").eq('id', store_id).execute()
    store = store_res.data[0]
    pickup_address = f"{store['address_street']}, {store['address_number']}, {store['address_city']} - {store['address_state']}"

    shipping_fee, error = uber.estimate_delivery(pickup_address, address)
    if error:
        print(f"Aviso Uber: {error}")
        shipping_fee = 15.00 # Fallback se a API falhar

    cart = session.get('cart', {})
    product_ids = list(cart.keys())
    products_res = supabase.table('products').select("*").in_('id', product_ids).execute()
    products = products_res.data

    subtotal = sum(float(p['price']) * cart[p['id']] for p in products)
    total = subtotal + shipping_fee

    order_data = {
        "store_id": store_id,
        "customer_id": customer['id'],
        "status": 'pending_payment',
        "subtotal": subtotal,
        "shipping_fee": shipping_fee,
        "total": total,
        "delivery_address": address
    }
    order_res = supabase.table('orders').insert(order_data).execute()
    order = order_res.data[0]

    # 4. Inserir Itens do Pedido
    order_items = []
    for p in products:
        order_items.append({
            "order_id": order['id'],
            "product_id": p['id'],
            "quantity": cart[p['id']],
            "unit_price": p['price']
        })
    supabase.table('order_items').insert(order_items).execute()

    # Limpar carrinho
    session.pop('cart', None)

    return redirect(url_for('order_confirmation', order_id=order['id']))

@app.route('/confirmacao/<order_id>')
def order_confirmation(order_id):
    order_res = supabase.table('orders').select("*, stores(*)").eq('id', order_id).execute()
    order = order_res.data[0]

    # Gerar Pix usando dados da LOJA
    pix_chave = order['stores'].get('pix_key') or "pendente@pix.com"
    pix_nome = order['stores'].get('pix_name') or order['stores'].get('name', 'VAPT VUPT')
    pix_cidade = order['stores'].get('pix_city') or "SAO PAULO"

    pix = PixGenerator(pix_chave, pix_nome, pix_cidade, float(order['total']))
    qr_code, payload = pix.generate_qr_base64()

    return render_template('confirmation.html', order=order, qr_code=qr_code, payload=payload)

# --- MARKETING E ADMIN ---

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        store = get_store()
        if store and store.get('admin_user') == username and store.get('admin_password') == password:
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('login.html', error="Usuário ou Senha incorretos")

    return render_template('login.html')

@app.route('/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/vendedor')
def admin_dashboard():
    if not check_auth(): return redirect(url_for('admin_login'))
    store = get_store()

    # Buscar pedidos
    orders_res = supabase.table('orders').select("*, customers(*)").eq('store_id', store['id']).order('created_at', desc=True).execute()
    orders = orders_res.data

    # Buscar produtos
    products_res = supabase.table('products').select("*").eq('store_id', store['id']).order('created_at', desc=True).execute()
    products = products_res.data

    return render_template('admin.html', store=store, orders=orders, products=products)

@app.route('/vendedor/produto/novo', methods=['POST'])
def admin_add_product():
    if not check_auth(): return redirect(url_for('admin_login'))
    store = get_store()

    # Lógica de Upload de Imagem
    image_url = request.form.get('image_url')
    file = request.files.get('file')

    if file and file.filename != '':
        # Gerar nome único para o arquivo
        ext = file.filename.split('.')[-1]
        filename = f"{uuid.uuid4()}.{ext}"
        bucket_name = "product-images"

        # Upload para Supabase Storage
        file_data = file.read()
        supabase.storage.from_(bucket_name).upload(filename, file_data, {"content-type": file.content_type})

        # Obter URL Pública
        image_url = supabase.storage.from_(bucket_name).get_public_url(filename)

    product_data = {
        "store_id": store_id,
        "name": request.form.get('name'),
        "description": request.form.get('description'),
        "price": float(request.form.get('price')),
        "weight_kg": float(request.form.get('weight', 0.5)),
        "image_url": image_url,
        "is_active": True
    }

    supabase.table('products').insert(product_data).execute()
    return redirect(url_for('admin_dashboard', slug=slug))

@app.route('/vendedor/produto/deletar/<product_id>')
def admin_delete_product(product_id):
    if not check_auth(): return redirect(url_for('admin_login'))
    supabase.table('products').delete().eq('id', product_id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/pedido/status', methods=['POST'])
def admin_update_order_status():
    if not check_auth(): return redirect(url_for('admin_login'))
    order_id = request.form.get('order_id')
    new_status = request.form.get('status')
    supabase.table('orders').update({"status": new_status}).eq('id', order_id).execute()
    return redirect(url_for('admin_dashboard'))

@app.route('/vendedor/configuracoes', methods=['POST'])
def admin_update_settings():
    if not check_auth(): return redirect(url_for('admin_login'))
    store = get_store()
    # Lógica de Upload de Logo
    logo_url = request.form.get('logo_url')
    file = request.files.get('file')

    if file and file.filename != '':
        ext = file.filename.split('.')[-1]
        filename = f"logo_{uuid.uuid4()}.{ext}"
        bucket_name = "product-images"
        file_data = file.read()
        supabase.storage.from_(bucket_name).upload(filename, file_data, {"content-type": file.content_type})
        logo_url = supabase.storage.from_(bucket_name).get_public_url(filename)

    store_data = {
        "name": request.form.get('name'),
        "whatsapp": request.form.get('whatsapp'),
        "logo_url": logo_url,
        "primary_color": request.form.get('primary_color'),
        "secondary_color": request.form.get('secondary_color'),
        "address_street": request.form.get('address_street'),
        "address_number": request.form.get('address_number'),
        "address_city": request.form.get('address_city'),
        "address_state": request.form.get('address_state'),
        "admin_user": request.form.get('admin_user'),
        "admin_password": request.form.get('admin_password'),
        "pix_key": request.form.get('pix_key'),
        "pix_name": request.form.get('pix_name'),
        "pix_city": request.form.get('pix_city')
    }
    supabase.table('stores').update(store_data).eq('id', store['id']).execute()
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
