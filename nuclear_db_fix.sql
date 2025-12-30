-- GARANTIR COLUNAS
ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_user TEXT DEFAULT 'admin';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_password TEXT DEFAULT 'vaptvupt123';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_key TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_name TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_city TEXT DEFAULT 'SAO PAULO';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS whatsapp_message TEXT DEFAULT 'Olá! Gostaria de falar sobre meu pedido no site.';

ALTER TABLE products ADD COLUMN IF NOT EXISTS stock_quantity INTEGER DEFAULT 99;

-- FORÇAR CREDENCIAIS
INSERT INTO stores (slug, name, whatsapp, admin_user, admin_password)
VALUES ('default', 'Venda Vapt Vupt', '5511999999999', 'admin', 'vaptvupt123')
ON CONFLICT (slug) DO UPDATE SET
    admin_user = EXCLUDED.admin_user,
    admin_password = EXCLUDED.admin_password;
