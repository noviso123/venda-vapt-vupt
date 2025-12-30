import psycopg2
import sys

# Tentativa via IP Direto do Pooler e Porta 6543 (Transaction Mode)
db_url = "postgresql://postgres.ffkaiyyrxtpsxvtienec:862485-Jhow@52.67.1.88:6543/postgres?sslmode=require"

sql_script = """
-- TABELA DE LOJAS (Multi-vendedor)
CREATE TABLE IF NOT EXISTS stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    whatsapp TEXT,
    logo_url TEXT,
    primary_color TEXT DEFAULT '#3B82F6',
    secondary_color TEXT DEFAULT '#10B981',
    is_active BOOLEAN DEFAULT true,
    address_street TEXT,
    address_number TEXT,
    address_city TEXT,
    address_state TEXT,
    address_zip TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- TABELA DE PRODUTOS
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

-- TABELA DE CLIENTES (Usuários Guest)
CREATE TABLE IF NOT EXISTS customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    whatsapp TEXT UNIQUE NOT NULL,
    name TEXT,
    email TEXT,
    address_full TEXT,
    zip_code TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- TABELA DE PEDIDOS
CREATE TABLE IF NOT EXISTS orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID REFERENCES stores(id),
    customer_id UUID REFERENCES customers(id),
    status TEXT DEFAULT 'pending_payment', -- pending_payment, paid, preparing, shipping, delivered, cancelled
    subtotal DECIMAL(10,2) NOT NULL,
    shipping_fee DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL,
    payment_method TEXT DEFAULT 'pix',
    payment_id TEXT, -- ID do Mercado Pago
    uber_delivery_id TEXT, -- ID da entrega na Uber
    tracking_url TEXT,
    delivery_address TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
);

-- ITENS DO PEDIDO
CREATE TABLE IF NOT EXISTS order_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID REFERENCES orders(id) ON DELETE CASCADE,
    product_id UUID REFERENCES products(id),
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price DECIMAL(10,2) NOT NULL
);

-- ÍNDICES PARA BUSCA RÁPIDA
CREATE INDEX IF NOT EXISTS idx_stores_slug ON stores(slug);
CREATE INDEX IF NOT EXISTS idx_products_store ON products(store_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
"""

def setup_db():
    try:
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()
        print("Conectado ao Supabase!")
        cur.execute(sql_script)
        conn.commit()
        print("Tabelas criadas com sucesso!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Erro ao configurar banco de dados: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup_db()
