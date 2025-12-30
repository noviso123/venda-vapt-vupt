-- Adicionar coluna para link externo opcional nos produtos
ALTER TABLE products ADD COLUMN IF NOT EXISTS external_url TEXT;

-- Garantir que a tabela de lojas tenha as chaves de Pix se não existirem
-- (Obs: Já devem existir pelos updates anteriores, mas é uma boa prática)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='stores' AND column_name='pix_key') THEN
        ALTER TABLE stores ADD COLUMN pix_key TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='stores' AND column_name='pix_name') THEN
        ALTER TABLE stores ADD COLUMN pix_name TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='stores' AND column_name='pix_city') THEN
        ALTER TABLE stores ADD COLUMN pix_city TEXT;
    END IF;
END $$;
