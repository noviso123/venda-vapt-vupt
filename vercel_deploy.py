import os
import requests
import json
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

TOKEN = "zVmVlxE3cQEmsCyPqrlR867F"
PROJECT_NAME = "vapt-vupt-loja"
REPO = "noviso123/venda-vapt-vupt"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def setup_vercel():
    print(f"--- Configurando Projeto {PROJECT_NAME} na Vercel ---")

    # 1. Criar Projeto na Vercel
    project_payload = {
        "name": PROJECT_NAME,
        "framework": None,
        "gitRepository": {
            "type": "github",
            "repo": REPO
        }
    }

    res = requests.post("https://api.vercel.com/v9/projects", headers=headers, json=project_payload, verify=False)
    if res.status_code in [200, 201]:
        print("Projeto criado/vinculado com sucesso!")
    else:
        print(f"Nota: Projeto já existe ou erro: {res.text}")

    # 2. Adicionar Variáveis de Ambiente
    envs = {
        "FLASK_ENV": "production",
        "SECRET_KEY": os.getenv("SECRET_KEY", "prod_secret_vapt123"),
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_ANON_KEY": os.getenv("SUPABASE_ANON_KEY"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "UBER_CLIENT_ID": os.getenv("UBER_CLIENT_ID"),
        "UBER_CLIENT_SECRET": os.getenv("UBER_CLIENT_SECRET"),
        "UBER_CUSTOMER_ID": os.getenv("UBER_CUSTOMER_ID"),
        "PIX_CHAVE": os.getenv("PIX_CHAVE"),
        "PIX_BENEFICIARIO": os.getenv("PIX_BENEFICIARIO"),
        "PIX_CIDADE": os.getenv("PIX_CIDADE")
    }

    for key, value in envs.items():
        if not value: continue
        env_payload = {
            "key": key,
            "value": value,
            "type": "plain",
            "target": ["production", "preview", "development"]
        }
        r = requests.post(f"https://api.vercel.com/v9/projects/{PROJECT_NAME}/env", headers=headers, json=env_payload, verify=False)
        if r.status_code in [200, 201]:
            print(f"Env {key} adicionada.")
        else:
            print(f"Env {key} já existe.")

    print("\n--- TUDO PRONTO! ---")
    print(f"URL Sugerida: https://{PROJECT_NAME}.vercel.app")

if __name__ == "__main__":
    setup_vercel()
