import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def check_credentials():
    print("--- Verificando Credenciais no Supabase ---")
    res = supabase.table('stores').select("*").eq('slug', 'default').execute()
    if res.data:
        store = res.data[0]
        print(f"Loja encontrada: {store['name']}")
        print(f"Usuário no Banco: '{store.get('admin_user')}'")
        print(f"Senha no Banco: '{store.get('admin_password')}'")
    else:
        print("ERRO: Nenhuma loja encontrada com slug 'default'.")

if __name__ == "__main__":
    check_credentials()
