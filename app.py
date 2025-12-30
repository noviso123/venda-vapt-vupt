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

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    # Listar todas as lojas (para o admin ou landing page)
    response = supabase.table('stores').select("*").execute()
    stores = response.data
    return render_template('index.html', stores=stores)

@app.route('/loja/<slug>')
def store_view(slug):
    # Buscar detalhes da loja
    store_res = supabase.table('stores').select("*").eq('slug', slug).execute()
    if not store_res.data:
        return "Loja não encontrada", 404

    store = store_res.data[0]

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

@app.route('/checkout/<store_slug>')
def checkout(store_slug):
    store_res = supabase.table('stores').select("*").eq('slug', store_slug).execute()
    store = store_res.data[0]

    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('store_view', slug=store_slug))

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

    # Gerar Pix
    pix_chave = os.getenv("PIX_CHAVE", "test@pix.com")
    pix_nome = os.getenv("PIX_BENEFICIARIO", "VENDA VAPT VUPT")
    pix_cidade = os.getenv("PIX_CIDADE", "SAO PAULO")

    pix = PixGenerator(pix_chave, pix_nome, pix_cidade, float(order['total']))
    qr_code, payload = pix.generate_qr_base64()

    return render_template('confirmation.html', order=order, qr_code=qr_code, payload=payload)

# --- MARKETING E ADMIN ---

@app.route('/bio/<slug>')
def instagram_bio(slug):
    # Redireciona para a loja com tracking (opcional)
    return redirect(url_for('store_view', slug=slug, src='instagram_bio'))

@app.route('/admin/<slug>')
def admin_dashboard(slug):
    # Buscar detalhes da loja
    store_res = supabase.table('stores').select("*").eq('slug', slug).execute()
    if not store_res.data: return "Acesso negado", 403
    store = store_res.data[0]

    # Buscar pedidos
    orders_res = supabase.table('orders').select("*, customers(*)").eq('store_id', store['id']).order('created_at', desc=True).execute()
    orders = orders_res.data

    # Buscar produtos
    products_res = supabase.table('products').select("*").eq('store_id', store['id']).order('created_at', desc=True).execute()
    products = products_res.data

    return render_template('admin.html', store=store, orders=orders, products=products)

@app.route('/admin/<slug>/produto/novo', methods=['POST'])
def admin_add_product(slug):
    store_res = supabase.table('stores').select("id").eq('slug', slug).execute()
    store_id = store_res.data[0]['id']

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

@app.route('/admin/<slug>/produto/deletar/<product_id>')
def admin_delete_product(slug, product_id):
    supabase.table('products').delete().eq('id', product_id).execute()
    return redirect(url_for('admin_dashboard', slug=slug))

@app.route('/admin/<slug>/pedido/status', methods=['POST'])
def admin_update_order_status(slug):
    order_id = request.form.get('order_id')
    new_status = request.form.get('status')
    supabase.table('orders').update({"status": new_status}).eq('id', order_id).execute()
    return redirect(url_for('admin_dashboard', slug=slug))

@app.route('/admin/<slug>/configuracoes', methods=['POST'])
def admin_update_settings(slug):
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
        "address_state": request.form.get('address_state')
    }
    supabase.table('stores').update(store_data).eq('slug', slug).execute()
    return redirect(url_for('admin_dashboard', slug=slug))

if __name__ == '__main__':
    app.run(debug=True)
