-- 1. TABELA DE LOJAS (Configurações Únicas)
CREATE TABLE IF NOT EXISTS stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'Minha Loja',
    whatsapp TEXT NOT NULL DEFAULT '5511999999999',
    logo_url TEXT,
    primary_color TEXT DEFAULT '#3B82F6',
    secondary_color TEXT DEFAULT '#10B981',
    is_active BOOLEAN DEFAULT true,

    -- Credenciais de Acesso
    admin_user TEXT DEFAULT 'admin',
    admin_password TEXT DEFAULT 'vaptvupt123',

    -- Pagamento (PIX)
    pix_key TEXT,
    pix_name TEXT,
    pix_city TEXT DEFAULT 'SAO PAULO',

    -- Logística (Uber Direct)
    address_street TEXT,
    address_number TEXT,
    address_city TEXT,
    address_state TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 2. TABELA DE PRODUTOS
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    image_url TEXT,
    weight_kg DECIMAL(5,3) DEFAULT 0.5,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 3. TABELA DE CLIENTES
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    whatsapp TEXT UNIQUE NOT NULL,
    name TEXT,
    address_full TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 4. TABELA DE PEDIDOS
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id),
    status TEXT DEFAULT 'pending_payment',
    subtotal DECIMAL(10,2) NOT NULL,
    shipping_fee DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL,
    delivery_address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- 5. ITENS DO PEDIDO
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_stores_slug ON stores(slug);
CREATE INDEX IF NOT EXISTS idx_products_store ON products(store_id);

-- Loja Inicial Default (Se não existir)
INSERT INTO stores (slug, name, whatsapp)
SELECT 'default', 'Venda Vapt Vupt', '5511999999999'
WHERE NOT EXISTS (SELECT 1 FROM stores WHERE slug = 'default');
