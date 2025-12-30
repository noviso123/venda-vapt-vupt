import os
import requests
import json
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

TOKEN = "zVmVlxE3cQEmsCyPqrlR867F"
PROJECT_NAME = "vapt-vupt-loja"
REPO_PATH = "noviso123/venda-vapt-vupt"
REPO_ID = "917527621"

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def final_push():
    print(f"--- Disparando Deploy Final Vercel ---")

    # 1. Tentar conectar Git corretamente
    link_url = f"https://api.vercel.com/v9/projects/{PROJECT_NAME}/link"
    link_data = {
        "link": {
            "type": "github",
            "repoId": REPO_ID,
            "orgId": None # Assume autodetect or not needed for personal accounts
        }
    }
    # Na verdade, a API v9/projects/{id} aceita o gitRepository no corpo.
    # Vamos tentar atualizar o projeto com o gitRepository primeiro.

    patch_url = f"https://api.vercel.com/v9/projects/{PROJECT_NAME}"
    patch_data = {
        "gitRepository": {
            "type": "github",
            "repo": REPO_PATH,
            "repoId": REPO_ID
        }
    }
    requests.patch(patch_url, headers=headers, json=patch_data, verify=False)

    # 2. Criar Deployment
    deploy_url = "https://api.vercel.com/v13/deployments"
    deploy_data = {
        "name": PROJECT_NAME,
        "gitSource": {
            "type": "github",
            "repoId": REPO_ID,
            "ref": "main"
        }
    }

    res = requests.post(deploy_url, headers=headers, json=deploy_data, verify=False)

    if res.status_code in [200, 201]:
        print(f"SUCESSO! Deploy iniciado.")
        print(f"URL: https://{PROJECT_NAME}.vercel.app")
    else:
        print(f"Erro no deploy final: {res.text}")

if __name__ == "__main__":
    final_push()
