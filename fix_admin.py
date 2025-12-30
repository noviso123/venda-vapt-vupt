import os
import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

# Configuração via REST direto para evitar problemas de SSL do SDK
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal"
}

def reset_admin():
    print("--- Resetando Credenciais Administrativas via REST API ---")

    # Atualizar loja 'default'
    update_data = {
        "admin_user": "admin",
        "admin_password": "vaptvupt123"
    }

    # PATCH /rest/v1/stores?slug=eq.default
    url = f"{SUPABASE_URL}/rest/v1/stores?slug=eq.default"

    try:
        res = requests.patch(url, headers=headers, json=update_data, verify=False)
        if res.status_code in [200, 201, 204]:
            print("SUCESSO: Credenciais resetadas para admin / vaptvupt123")
        else:
            print(f"ERRO: Resposta da API: {res.status_code} - {res.text}")

            # Tentar Insert se não existir
            print("Tentando Insert caso a loja não exista...")
            insert_data = {
                "slug": "default",
                "name": "Venda Vapt Vupt",
                "whatsapp": "5511999999999",
                "admin_user": "admin",
                "admin_password": "vaptvupt123"
            }
            res_ins = requests.post(f"{SUPABASE_URL}/rest/v1/stores", headers=headers, json=insert_data, verify=False)
            print(f"Resultado Insert: {res_ins.status_code}")

    except Exception as e:
        print(f"Falha na comunicação: {e}")

if __name__ == "__main__":
    reset_admin()
