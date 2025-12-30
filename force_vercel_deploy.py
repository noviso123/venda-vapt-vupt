import os
import requests
import json
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

TOKEN = "zVmVlxE3cQEmsCyPqrlR867F"
PROJECT_NAME = "vapt-vupt-loja"
REPO_ID = "917527621" # ID fixo do repositório noviso123/venda-vapt-vupt

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

def force_deploy():
    print(f"--- Forçando Deploy do Projeto {PROJECT_NAME} ---")

    # 1. Obter ID do Projeto na Vercel
    res = requests.get(f"https://api.vercel.com/v9/projects/{PROJECT_NAME}", headers=headers, verify=False)
    if res.status_code != 200:
        print(f"Erro ao buscar projeto: {res.text}")
        return

    project_id = res.json()['id']
    print(f"Project ID: {project_id}")

    # 2. Criar um Deployment Direto
    deploy_payload = {
        "name": PROJECT_NAME,
        "project": project_id,
        "gitSource": {
            "type": "github",
            "repoId": REPO_ID,
            "ref": "main"
        }
    }

    res_deploy = requests.post("https://api.vercel.com/v13/deployments", headers=headers, json=deploy_payload, verify=False)

    if res_deploy.status_code in [200, 201]:
        deploy_data = res_deploy.json()
        print(f"Deploy iniciado com sucesso! ID: {deploy_data['id']}")
        print(f"URL de Produção: https://{PROJECT_NAME}.vercel.app")
    else:
        print(f"Erro ao disparar deploy: {res_deploy.text}")

if __name__ == "__main__":
    force_deploy()
