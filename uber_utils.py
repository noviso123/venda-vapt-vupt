import requests
import os
from dotenv import load_dotenv

load_dotenv()

class UberDirect:
    def __init__(self):
        self.client_id = os.getenv("UBER_CLIENT_ID")
        self.client_secret = os.getenv("UBER_CLIENT_SECRET")
        self.customer_id = os.getenv("UBER_CUSTOMER_ID")
        self.base_url = "https://api.uber.com/v1/delivery"
        self.auth_url = "https://auth.uber.com/oauth/v2/token"

    def get_token(self):
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials',
            'scope': 'direct.delivery'
        }
        res = requests.post(self.auth_url, data=payload)
        if res.status_code == 200:
            return res.json().get('access_token')
        return None

    def estimate_delivery(self, pickup_address, dropoff_address):
        token = self.get_token()
        if not token:
            return None, "Erro na autenticação Uber"

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # Payload simplificado para estimativa
        data = {
            "pickup_address": pickup_address,
            "dropoff_address": dropoff_address,
            "customer_id": self.customer_id
        }

        # Endpoint de cotação (Quote)
        res = requests.post(f"{self.base_url}/quote", headers=headers, json=data)

        if res.status_code == 200:
            quote = res.json()
            return quote.get('fee') / 100, None # Uber cost is in cents

        return 15.00, f"Erro Uber: {res.text}" # Valor padrão caso falhe

if __name__ == "__main__":
    uber = UberDirect()
    print(uber.get_token())
