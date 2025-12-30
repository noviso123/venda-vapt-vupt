import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def force_update_creds():
    print("--- Forçando Atualização de Credenciais no Banco ---")
    try:
        # Tentar atualizar a loja padrão
        res = supabase.table('stores').update({
            "admin_user": "admin",
            "admin_password": "admin"
        }).eq('slug', 'default').execute()

        if res.data:
            print("SUCESSO: Credenciais atualizadas no banco de dados (admin/admin)")
        else:
            print("AVISO: Loja 'default' não encontrada para atualizar.")

    except Exception as e:
        print(f"ERRO ao atualizar banco: {e}")

if __name__ == "__main__":
    force_update_creds()
