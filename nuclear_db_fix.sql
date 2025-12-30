-- 1. DROP E CREATE (Para garantir que não haja lixo de colunas antigas)
-- CUIDADO: Isso reseta as configurações da loja, mas garante o funcionamento.
-- Se preferir não deletar, use apenas os comandos ALTER TABLE abaixo.

-- Garantir que as colunas existam
ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_user TEXT DEFAULT 'admin';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS admin_password TEXT DEFAULT 'vaptvupt123';
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_key TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_name TEXT;
ALTER TABLE stores ADD COLUMN IF NOT EXISTS pix_city TEXT DEFAULT 'SAO PAULO';

-- FORÇAR AS CREDENCIAIS NA LOJA DEFAULT
-- Primeiro garante que a linha existe
INSERT INTO stores (slug, name, whatsapp, admin_user, admin_password)
VALUES ('default', 'Venda Vapt Vupt', '5511999999999', 'admin', 'vaptvupt123')
ON CONFLICT (slug) DO UPDATE SET
    admin_user = EXCLUDED.admin_user,
    admin_password = EXCLUDED.admin_password;

-- 2. Limpar cache de esquema do Supabase (Ocorre automaticamente ao rodar SQL no Dashboard)
-- Selecione para conferir se deu certo:
-- SELECT slug, admin_user, admin_password FROM stores;
