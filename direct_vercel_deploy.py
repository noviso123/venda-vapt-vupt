import os
import requests
import json
import urllib3
import base64
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
load_dotenv()

TOKEN = "zVmVlxE3cQEmsCyPqrlR867F"
PROJECT_NAME = "vapt-vupt-loja"
ROOT_DIR = "." # Diretório atual do projeto

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def direct_deploy():
    print(f"--- Iniciando Deploy Direto (File Upload) na Vercel ---")

    files_to_deploy = []

    # Listar arquivos essenciais (ignorando lixos)
    whitelist = [
        "app.py", "requirements.txt", "vercel.json", "pix_utils.py",
        "setup_db.sql", ".env", "templates/base.html", "templates/store.html",
        "templates/checkout.html", "templates/confirmation.html",
        "templates/admin.html", "templates/login.html"
    ]

    # Adicionar subpastas
    for root, dirs, files in os.walk(ROOT_DIR):
        if ".git" in root or "__pycache__" in root or ".gemini" in root:
            continue

        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), ROOT_DIR).replace("\\", "/")
            if rel_path in whitelist or rel_path.startswith("templates/"):
                with open(os.path.join(root, file), "rb") as f:
                    content = f.read()
                    files_to_deploy.append({
                        "file": rel_path,
                        "data": base64.b64encode(content).decode('utf-8'),
                        "encoding": "base64"
                    })

    deploy_payload = {
        "name": PROJECT_NAME,
        "files": files_to_deploy,
        "target": "production",
        "projectSettings": {
            "framework": None
        }
    }

    print(f"Enviando {len(files_to_deploy)} arquivos...")
    res = requests.post("https://api.vercel.com/v13/deployments", headers=headers, json=deploy_payload, verify=False)

    if res.status_code in [200, 201]:
        data = res.json()
        print(f"SUCESSO! Deploy iniciado.")
        print(f"URL: https://{PROJECT_NAME}.vercel.app")
    else:
        print(f"Erro no deploy direto: {res.text}")

if __name__ == "__main__":
    direct_deploy()
