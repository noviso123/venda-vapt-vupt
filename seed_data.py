import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(url, key)

def seed():
    print("Iniciando cadastro de dados de teste...")

    # 1. Criar Loja de Teste
    store_data = {
        "name": "Loja Vapt Vupt Demo",
        "slug": "demo",
        "whatsapp": "5511999999999",
        "primary_color": "#4F46E5", # Indigo 600
        "secondary_color": "#10B981", # Emerald 500
        "address_street": "Av. Paulista",
        "address_number": "1000",
        "address_city": "São Paulo",
        "address_state": "SP",
        "address_zip": "01310-100"
    }

    try:
        store_res = supabase.table('stores').upsert(store_data, on_conflict='slug').execute()
        store = store_res.data[0]
        print(f"Loja '{store['name']}' criada com sucesso!")

        # 2. Criar Produtos de Teste
        products = [
            {
                "store_id": store['id'],
                "name": "Fone de Ouvido Bluetooth",
                "description": "Fone com cancelamento de ruído e 20h de bateria.",
                "price": 199.90,
                "weight_kg": 0.3
            },
            {
                "store_id": store['id'],
                "name": "Carregador Rápido 20W",
                "description": "Carregador USB-C compatível com iPhone e Android.",
                "price": 89.90,
                "weight_kg": 0.1
            },
            {
                "store_id": store['id'],
                "name": "Cabo USB-C Premium",
                "description": "Cabo reforçado de 2 metros com alta velocidade.",
                "price": 45.00,
                "weight_kg": 0.05
            }
        ]

        supabase.table('products').upsert(products).execute()
        print(f"{len(products)} produtos cadastrados com sucesso!")
        print("\n--- TUDO PRONTO! ---")
        print(f"Acesse: http://127.0.0.1:5000/loja/demo")

    except Exception as e:
        print(f"Erro ao inserir dados: {e}")
        print("DICA: Você já rodou o SQL no painel do Supabase?")

if __name__ == "__main__":
    seed()
