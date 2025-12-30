-- 1. TABELA DE LOJAS
CREATE TABLE IF NOT EXISTS stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL DEFAULT 'default',
    name TEXT NOT NULL DEFAULT 'Minha Loja',
    whatsapp TEXT NOT NULL DEFAULT '5511999999999',
    logo_url TEXT,
    primary_color TEXT DEFAULT '#3B82F6',
    secondary_color TEXT DEFAULT '#10B981',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- GARANTIR COLUNAS (Fase 6)
ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_user TEXT DEFAULT 'admin';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_password TEXT DEFAULT 'vaptvupt123';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_key TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_name TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_city TEXT DEFAULT 'SAO PAULO';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS whatsapp_message TEXT DEFAULT 'Olá! Gostaria de falar sobre meu pedido no site.';

-- 2. TABELA DE PRODUTOS
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    image_url TEXT,
    weight_kg DECIMAL(5,3) DEFAULT 0.5,
    stock_quantity INTEGER DEFAULT 99, -- NOVO: ESTOQUE
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

-- Loja Inicial Default
INSERT INTO stores (slug, name, whatsapp)
SELECT 'default', 'Venda Vapt Vupt', '5511999999999'
WHERE NOT EXISTS (SELECT 1 FROM stores WHERE slug = 'default');

-- Garantir acesso
UPDATE stores SET admin_user = 'admin', admin_password = 'vaptvupt123'
WHERE slug = 'default' AND (admin_user IS NULL OR admin_user = '');
