-- Adicionar coluna is_active se não existir
ALTER TABLE products ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- Garantir que todos os produtos existentes estejam ativos
UPDATE products SET is_active = TRUE WHERE is_active IS NULL;
