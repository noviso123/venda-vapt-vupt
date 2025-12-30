-- ==========================================
-- FULL DATABASE SETUP - VENDA VAPT VUPT
-- Copie e cole no SQL Editor do Supabase
-- ==========================================

-- 1. Tabela de Lojas (Stores)
CREATE TABLE IF NOT EXISTS stores (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT,
    logo_url TEXT,
    whatsapp TEXT,
    whatsapp_message TEXT,
    primary_color TEXT DEFAULT '#0EA5E9',
    secondary_color TEXT DEFAULT '#0284C7',
    pix_key TEXT,
    pix_name TEXT,
    pix_city TEXT,
    admin_user TEXT DEFAULT 'admin',
    admin_password TEXT DEFAULT 'admin',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Tabela de Clientes (Customers)
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email TEXT UNIQUE,
    name TEXT,
    phone TEXT,
    password TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. Tabela de Produtos (Products)
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT,
    price DECIMAL(10,2) DEFAULT 0.00,
    image_url TEXT,
    external_url TEXT,
    stock_quantity INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    clicks_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Tabela de Imagens Extras (Product Images)
CREATE TABLE IF NOT EXISTS product_images (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    image_url TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. Tabela de Pedidos (Orders)
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    store_id UUID REFERENCES stores(id) ON DELETE CASCADE,
    customer_id UUID REFERENCES customers(id),
    total DECIMAL(10,2) DEFAULT 0.00,
    status TEXT DEFAULT 'pending_payment',
    delivery_address TEXT,
    payment_method TEXT DEFAULT 'pix',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 6. RPC para automação de schema (Caso precise via código)
CREATE OR REPLACE FUNCTION add_column_if_not_exists(t_name TEXT, c_name TEXT, c_type TEXT)
RETURNS void AS $$
BEGIN
    EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS %I %s', t_name, c_name, c_type);
END;
$$ LANGUAGE plpgsql;

-- 7. Buckets de Storage (Execute manualmente no Dashboard se falhar)
-- Certifique-se de criar o bucket 'product-images' como PÚBLICO.
