import os
import urllib.parse
import requests
import re
from flask import Flask, render_template, request, session, redirect, url_for, jsonify
from dotenv import load_dotenv
from supabase import create_client, Client
from pix_utils import PixGenerator
import uuid
import urllib3
import httpx
import ssl
from supabase.lib.client_options import ClientOptions

# --- SOLUÇÃO NUCLEAR SSL (Monkeypatch Global httpx + ssl) ---
# Força o Python e o httpx (Supabase) a ignorar a verificação de certificados.
# Essencial para ambientes com proxys/firewalls que interceptam tráfego HTTPS causando "self-signed certificate".

# 1. Patch para bibliotecas que usam o módulo ssl padrão (requests, etc)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError: pass
else: ssl._create_default_https_context = _create_unverified_https_context

# 2. Patch agressivo para HTTPX (usado pelo Supabase-py)
# Redefinimos o construtor do Client para sempre ignorar SSL
original_client_init = httpx.Client.__init__
def patched_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_client_init(self, *args, **kwargs)
httpx.Client.__init__ = patched_client_init

# Também para AsyncClient por segurança
original_async_client_init = httpx.AsyncClient.__init__
def patched_async_client_init(self, *args, **kwargs):
    kwargs['verify'] = False
    original_async_client_init(self, *args, **kwargs)
httpx.AsyncClient.__init__ = patched_async_client_init

# Desabilitar avisos de SSL (InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "prod_secret_vapt123")
app.config['PERMANENT_SESSION_LIFETIME'] = 60 * 60 * 24 * 7  # 7 dias
app.config['SESSION_PERMANENT'] = True
# SESSION_TYPE removido para usar cookies padrão (melhor para Vercel)

# Configuração Supabase com Bypass de SSL para httpx (Postgrest/Storage)
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Injetar verify=False nas opções do cliente
# Nota: Como ClientOptions não aceita verify diretamente em algumas versões,
# mantemos as opções padrão e garantimos que o httpx ignore SSL se houver erro global.
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
            {'t_name': 'stores', 'c_name': 'pix_city', 'c_type': 'TEXT'},
            {'t_name': 'stores', 'c_name': 'admin_user', 'c_type': 'TEXT DEFAULT \'admin\''},
            {'t_name': 'stores', 'c_name': 'admin_password', 'c_type': 'TEXT DEFAULT \'admin\''},
            {'t_name': 'customers', 'c_name': 'password', 'c_type': 'TEXT'}
        ]
        for col in rpc_cols:
            try: supabase.rpc('add_column_if_not_exists', col).execute()
            except: pass

        # Forçar admin/admin no default se não existir
        try:
            check = supabase.table('stores').select("admin_user").eq('slug', 'default').execute()
            if check.data and not check.data[0].get('admin_user'):
                supabase.table('stores').update({"admin_user": "admin", "admin_password": "admin"}).eq('slug', 'default').execute()
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

def check_auth():
    return session.get('is_admin') or session.get('is_superadmin')

def is_superadmin():
    return session.get('is_superadmin', False)

def generate_wa_link(phone, base_msg, cart_items=None, total=None):
    msg = base_msg
    if cart_items:
        msg += "\n\n📋 *MEU PEDIDO:*\n"
        for item in cart_items:
            msg += f"- {item['quantity']}x {item['name']}\n"
        if total: msg += f"\n💰 *TOTAL:* R$ {total:.2f}"
    return f"https://wa.me/{phone}?text={urllib.parse.quote(msg)}"

def download_and_persist_image(image_url, prefix="img"):
    """
    Baixa imagem de URL externa, valida e persiste no Supabase Storage.
    Retorna URL pública do storage ou None se falhar.
    """
    try:
        # 1. Download com timeout e fallback para SSL se necessário
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        try:
            response = requests.get(image_url, headers=headers, timeout=15, stream=True)
        except requests.exceptions.SSLError:
            response = requests.get(image_url, headers=headers, timeout=15, stream=True, verify=False)

        if response.status_code != 200:
            app.logger.warning(f"Falha download imagem: {response.status_code} - {image_url}")
            return None

        # 2. Verificar tamanho (max 10MB)
        content_length = response.headers.get('content-length')
        if content_length and int(content_length) > 10 * 1024 * 1024:
            app.logger.warning(f"Imagem muito grande: {content_length} bytes - {image_url}")
            return None

        image_data = response.content

        # 3. Validar MIME básico
        content_type = response.headers.get('content-type', '')
        if not any(t in content_type.lower() for t in ['image/', 'jpeg', 'png', 'webp', 'gif']):
            # Verificar magic bytes
            if not (image_data[:3] == b'\xff\xd8\xff' or  # JPEG
                    image_data[:8] == b'\x89PNG\r\n\x1a\n' or  # PNG
                    image_data[:4] == b'RIFF' or  # WebP
                    image_data[:6] in (b'GIF87a', b'GIF89a')):  # GIF
                app.logger.warning(f"Arquivo não é imagem válida: {content_type} - {image_url}")
                return None

        # 4. Determinar extensão
        ext = 'jpg'
        if b'\x89PNG' in image_data[:10]: ext = 'png'
        elif b'RIFF' in image_data[:10]: ext = 'webp'
        elif b'GIF8' in image_data[:10]: ext = 'gif'

        # 5. Gerar nome único e fazer upload
        filename = f"{prefix}_{uuid.uuid4()}.{ext}"

        supabase.storage.from_('product-images').upload(filename, image_data, {"content-type": f"image/{ext}"})

        # 6. Retornar URL pública
        public_url = supabase.storage.from_('product-images').get_public_url(filename)
        app.logger.info(f"Imagem persistida: {filename} de {image_url}")
        return public_url

    except Exception as e:
        app.logger.error(f"Erro ao persistir imagem {image_url}: {e}")
        return None


# --- ROTAS VITRINE ---
@app.route('/')
def index():
    store = get_store()
    query = request.args.get('q', '').strip()
    products = []
    try:
        # VITRINE GLOBAL: Pega produtos de TODAS as lojas para máxima exposição
        req = supabase.table('products').select("*, product_images(*), stores(*)").eq('is_active', True)
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
        try:
            # Limpeza básica e coleta de dados
            form = {k: v.strip() for k, v in request.form.items()}

            address_details = f"{form.get('street')}, {form.get('number')}"
            if form.get('complement'): address_details += f" - {form.get('complement')}"
            address_details += f", {form.get('neighborhood')}, {form.get('city')} - {form.get('state')} (CEP: {form.get('cep')})"

            customer_data = {
                "name": form.get('name'),
                "email": form.get('email'),
                "whatsapp": form.get('whatsapp'),
                "password": form.get('password'),
                "address_full": address_details
            }

            app.logger.info(f"Tentando cadastrar cliente: {customer_data['whatsapp']}")

            # Usar upsert para evitar erro de UNIQUE no whatsapp, permitindo "atualizar" se já existir
            res = supabase.table('customers').upsert(customer_data, on_conflict="whatsapp").execute()

            if res.data:
                app.logger.info(f"Cliente cadastrado/atualizado com sucesso: {res.data[0]['id']}")
                session.permanent = True
                session['customer_id'] = res.data[0]['id']
                session['customer_name'] = res.data[0]['name']

                if session.get('cart'):
                    return redirect(url_for('checkout'))
                return redirect(url_for('customer_orders'))
            else:
                app.logger.warning("Falha no insert: Nenhum dado retornado do Supabase.")
                return render_template('register.html', error="Erro ao processar cadastro no servidor.")

        except Exception as e:
            app.logger.error(f"Erro fatal no Cadastro: {str(e)}")
            return render_template('register.html', error=f"Erro ao cadastrar: {str(e)}")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        login_id = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        store = get_store()

        app.logger.info(f"Tentativa de login: {login_id}")

        # 1. Login Superadmin
        super_pass = os.getenv("SUPERADMIN_PASSWORD", "super1234").strip()
        app.logger.info(f"DEBUG: Superadmin esperado: superadmin / {super_pass}")

        if login_id == 'superadmin' and password == super_pass:
            app.logger.info("Login Superadmin SUCESSO")
            session.clear() # Limpar sessões anteriores
            session.permanent = True
            session['is_superadmin'] = True
            session['is_admin'] = True
            return redirect(url_for('admin_dashboard'))

        # 2. Login Admin da Loja
        if store:
            stored_pass = store.get('admin_password', 'admin').strip()
            app.logger.info(f"DEBUG: Admin esperado para loja: admin / {stored_pass}")

            if login_id == 'admin' and password == stored_pass:
                app.logger.info("Login Admin SUCESSO")
                session.clear()
                session.permanent = True
                session['is_admin'] = True
                session['is_superadmin'] = False
                return redirect(url_for('admin_dashboard'))

        # 3. Login Cliente
        try:
            c_res = supabase.table('customers').select("*").eq('email', login_id).eq('password', password).execute()
            if not c_res.data:
                c_res = supabase.table('customers').select("*").eq('whatsapp', login_id).eq('password', password).execute()

            if c_res.data:
                app.logger.info(f"Login Cliente SUCESSO: {c_res.data[0]['name']}")
                session.clear()
                session.permanent = True
                session['customer_id'] = c_res.data[0]['id']
                session['customer_name'] = c_res.data[0]['name']
                if session.get('cart'): return redirect(url_for('checkout'))
                return redirect(url_for('customer_orders'))
        except Exception as e:
            app.logger.error(f"Erro login cliente: {e}")

        app.logger.warning(f"Login FALHOU para: {login_id}")
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
    session.pop('is_superadmin', None)
    session.pop('customer_id', None)
    session.pop('customer_name', None)
    return redirect(url_for('index'))

@app.route('/vendedor')
def admin_dashboard():
    if not check_auth(): return redirect(url_for('admin_login'))

    # Dashboard para Superadmin (BI Global)
    if is_superadmin():
        try:
            stores = supabase.table('stores').select("*").execute().data
            orders_all = supabase.table('orders').select("total, status").execute().data

            # BI Superadmin
            total_sales = sum(o['total'] for o in orders_all if o['status'] != 'cancelled')
            total_orders = len(orders_all)
            avg_ticket = total_sales / total_orders if total_orders > 0 else 0

            return render_template('super_admin.html',
                                 stores=stores,
                                 total_sales=total_sales,
                                 total_orders=total_orders,
                                 avg_ticket=avg_ticket)
        except Exception as e:
            app.logger.error(f"Erro Carregar Super Panel: {e}")

    # Dashboard para Vendedor (Sua própria loja + BI Local)
    store = get_store()
    orders, products = [], []
    stats = {"total_revenue": 0, "order_count": 0, "product_count": 0}

    if store and store.get('id') != "00000000-0000-0000-0000-000000000000":
        try:
            orders = supabase.table('orders').select("*, customers(*)").eq('store_id', store['id']).order('created_at', desc=True).execute().data
            products = supabase.table('products').select("*, product_images(*)").eq('store_id', store['id']).order('created_at', desc=True).execute().data

            # BI Local
            stats["total_revenue"] = sum(o['total'] for o in orders if o['status'] != 'cancelled')
            stats["order_count"] = len(orders)
            stats["product_count"] = len(products)
        except: pass

    return render_template('admin.html', store=store, orders=orders, products=products, stats=stats)

@app.route('/vendedor/configuracoes', methods=['POST'])
def update_settings():
    if not check_auth(): return redirect(url_for('admin_login'))

    try:
        # O admin_user deve ser sempre 'admin' para vendedores, conforme solicitado
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
            "admin_user": "admin"  # FIXO: Admin sempre será admin
        }

        # Só atualiza a senha se for fornecida
        if request.form.get('admin_password'):
            store_data["admin_password"] = request.form.get('admin_password')
        file = request.files.get('file')
        if file and file.filename:
            try:
                filename = f"logo_{uuid.uuid4()}.{file.filename.split('.')[-1]}"
                supabase.storage.from_('product-images').upload(filename, file.read())
                store_data["logo_url"] = supabase.storage.from_('product-images').get_public_url(filename)
            except: pass

        # Upsert com proteção de erro
        supabase.table('stores').upsert(dict(store_data, slug="default")).execute()
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        app.logger.error(f"Erro ao salvar configurações: {e}")
        return render_template('error.html', error=f"Erro ao salvar: {str(e)}", store=get_store())

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
                    img_rows = []
                    for i, img_url in enumerate(images_list):
                        # Se já é URL do Supabase Storage, não baixar novamente
                        if 'supabase' in img_url.lower() or 'storage' in img_url.lower():
                            final_url = img_url
                        else:
                            # Baixar e persistir imagem externa no Storage
                            persisted_url = download_and_persist_image(img_url, prefix=f"prod_{new_prod_id}")
                            final_url = persisted_url if persisted_url else img_url
                        img_rows.append({"product_id": new_prod_id, "image_url": final_url, "display_order": i})
                    if img_rows:
                        supabase.table('product_images').insert(img_rows).execute()
            except Exception as e:
                app.logger.error(f"Erro ao processar imagens extras: {e}")

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

def optimize_marketing_data(raw_data):
    """
    IA de Marketing: Otimiza título e descrição para venda profissional.
    """
    title = raw_data.get('title', '').strip()
    desc = raw_data.get('description', '').strip()

    # 1. Otimização de Título (Magnético)
    if title:
        # Remover lixo comum de SEO/venda (OBS: escapar o pipe | para não remover espaços)
        cleanups = [
            r" - .*?$", r" \| .*?$", r" lojas? oficial$", r" frete grátis.*$",
            r" cupom de desconto.*$", r" compre aqui.*$", r" melhor preço.*$",
            r" parcelas? sem juros.*$", r" até \d+x.*$"
        ]
        for pattern in cleanups:
            title = re.sub(pattern, "", title, flags=re.I).strip()

        # Se for muito longo, resumir mantendo apenas as primeiras palavras (Marca + Modelo)
        if len(title) > 60:
            words = title.split()
            title = " ".join(words[:10]) # Primeiras 10 palavras ou 60 chars
            if len(title) > 57: title = title[:57] + "..."

        # Title Case amigável e limpeza de espaços extras
        title = re.sub(r'\s+', ' ', title).strip()
        if title.isupper() or title.islower():
            title = title.title()

    # 2. Otimização de Descrição (Structure & Copywriting)
    if desc:
        # Limpar excesso de HTML/Espaços
        desc = re.sub(r'<[^>]+>', '', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()

        # Identificar se já tem bullets ou criar estrutura
        points = []
        # Tentar quebrar por pontos ou frases longas para criar bullets
        potential_points = re.split(r'[;.]', desc)
        for p in potential_points:
            p = p.strip()
            if len(p) > 20 and len(points) < 5:
                # Adicionar emoji de destaque se não tiver
                points.append(f"✨ {p}")

        # Construir Copy
        intro = "💎 **Oportunidade Premium**\n\n"
        if len(points) > 0:
            body = "\n".join(points)
        else:
            body = desc[:300]

        footer = "\n\n🚀 *Garanta o seu hoje mesmo! Estoque limitado.*"

        desc = f"{intro}{body}{footer}"

    return title, desc

@app.route('/vendedor/fetch-metadata')
def fetch_metadata():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    url_to_fetch = request.args.get('url')
    if not url_to_fetch: return jsonify({"error": "no url"}), 400

    try:
        from bs4 import BeautifulSoup
        import requests

        headers = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36' }

        try:
            response = requests.get(url_to_fetch, headers=headers, timeout=15)
        except requests.exceptions.SSLError:
            app.logger.warning(f"SSL falhou para {url_to_fetch}, tentando sem verificar cert...")
            response = requests.get(url_to_fetch, headers=headers, timeout=15, verify=False)

        response.raise_for_status()
        html = response.text
        soup = BeautifulSoup(html, 'lxml')

        data = { "title": "", "description": "", "price": 0.0, "original_price": 0.0, "images": [], "video": "", "stock": 1 }

        # 1. Tentar JSON-LD (Product)
        import json
        for script in soup.find_all('script', type='application/ld+json'):
            try:
                ld_text = script.string.strip()
                if not ld_text: continue
                ld = json.loads(ld_text)
                if isinstance(ld, list): ld = ld[0]

                target = None
                if ld.get('@type') == 'Product': target = ld
                elif '@graph' in ld:
                    for item in ld['@graph']:
                        if item.get('@type') == 'Product': target = item; break

                if target:
                    data["title"] = target.get('name', '')
                    data["description"] = target.get('description', '')
                    offers = target.get('offers')
                    if isinstance(offers, dict):
                        data["price"] = float(offers.get('price', 0))
                    elif isinstance(offers, list) and len(offers) > 0:
                        data["price"] = float(offers[0].get('price', 0))

                    imgs = target.get('image')
                    if isinstance(imgs, str): data["images"].append(imgs)
                    elif isinstance(imgs, list): data["images"].extend(imgs)
                    break
            except: pass

        # 2. Meta Tags Fallback & Imagens
        if not data["title"]:
            tag = soup.find('meta', property='og:title') or soup.find('meta', attrs={'name': 'twitter:title'}) or soup.find('title')
            data["title"] = tag.get('content') if tag and tag.name == 'meta' else (tag.text if tag else "")

        if not data["description"]:
            tag = soup.find('meta', property='og:description') or soup.find('meta', attrs={'name': 'description'})
            data["description"] = tag.get('content') if tag else ""

        # === EXTRAÇÃO DE PREÇO AVANÇADA ===
        if not data["price"] or data["price"] == 0:
            # 1. Tentar meta tags específicas de valor
            price_tag = soup.find('meta', property='product:price:amount') or \
                        soup.find('meta', property='og:price:amount') or \
                        soup.find('meta', attrs={'name': 'twitter:data1'})

            if price_tag:
                try:
                    val = price_tag.get('content') or price_tag.get('value')
                    data["price"] = float(re.sub(r'[^\d.]', '', val.replace(',', '.')))
                except: pass

        if not data["price"] or data["price"] == 0:
            # 2. Procurar em seletores comuns de e-commerce
            selectors = [
                 '.price', '.current-price', '#priceblock_ourprice', '#priceblock_dealprice',
                 '.vtex-product-summary-2-x-currencyInteger', '.valor-por', '.price-tag-fraction',
                 '[itemprop="price"]', '.product-price', '.sales-price'
            ]
            for sel in selectors:
                el = soup.select_one(sel)
                if el:
                    try:
                        val = el.get_text(strip=True)
                        data["price"] = float(re.sub(r'[^\d.]', '', val.replace('.', '').replace(',', '.')))
                        if data["price"] > 0: break
                    except: pass

        if not data["price"] or data["price"] == 0:
            # 3. Regex exaustiva no corpo do texto (Fallback final)
            price_patterns = [
                r'R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})',
                r'R\$\s?(\d+,\d{2})'
            ]
            text = soup.get_text()
            for pattern in price_patterns:
                match = re.search(pattern, text)
                if match:
                    try:
                        val = match.group(1).replace('.', '').replace(',', '.')
                        data["price"] = float(val)
                        if data["price"] > 0: break
                    except: pass

        data["price"] = round(float(data["price"] or 0), 2)
        data["original_price"] = data["price"] # Guardar para sugestão

        # 3. EXTRAÇÃO DE IMAGENS PREMIUM
        found_imgs = []
        og_img = soup.find('meta', property='og:image')
        if og_img: found_imgs.append(og_img.get('content'))

        for img in soup.find_all('img', src=True):
            src = img.get('src')
            if not src.startswith('http'):
                from urllib.parse import urljoin
                src = urljoin(url_to_fetch, src)

            # Filtro inteligente: excluir imagens pequenas ou sem contexto de produto
            alt = img.get('alt', '').lower()
            width = img.get('width', '100')
            try: w = int(re.sub(r'\D', '', width))
            except: w = 100

            if any(x in src.lower() or x in alt for x in ['icon', 'logo', 'button', 'sprite', 'pixel', 'banner']): continue
            if w < 50: continue # Provável ícone
            found_imgs.append(src)

        data["images"] = list(dict.fromkeys(found_imgs))

        # === CAMADA DE INTELIGÊNCIA DE MARKETING ===
        opt_title, opt_desc = optimize_marketing_data(data)
        data["title"] = opt_title
        data["description"] = opt_desc

        # Finalizar Preço
        data["price"] = round(float(data["price"] or 0), 2)

        # Video
        og_vid = soup.find('meta', property='og:video')
        if og_vid: data["video"] = og_vid.get('content')

        # === PERSISTÊNCIA NO STORAGE ===
        persisted_images = []
        main_image_persisted = ""

        for i, img_url in enumerate(data["images"][:5]):
            try:
                # Sufixo informativo para o log
                persisted_url = download_and_persist_image(img_url, prefix=f"expert_{uuid.uuid4().hex[:6]}")
                if persisted_url:
                    persisted_images.append(persisted_url)
                    if i == 0: main_image_persisted = persisted_url
                else: persisted_images.append(img_url)
            except: persisted_images.append(img_url)

        return jsonify({
            "title": data["title"],
            "description": data["description"],
            "image": main_image_persisted,
            "images": persisted_images,
            "video": data["video"],
            "price": data["price"],
            "original_price": data["original_price"],
            "stock": 1,
            "images_persisted": True
        })

    except Exception as e:
        app.logger.error(f"Erro Scraper Inteligente: {e}")
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
