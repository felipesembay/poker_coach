import requests
import pandas as pd
import time

name = "Eliana_alves40"
url = f"https://pt.sharkscope.com/poker-statistics/networks/PartyPoker/players/{name}&Currency=BRL"
headers = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://www.sharkscope.com.br",
}

def get_player_stats(name):
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Lança erro para status HTTP 4xx/5xx
        
        # Parseia a resposta JSON
        data = response.json()
        
        # Extrair dados (ajuste conforme a estrutura real da resposta)
        stats = {
            "name": name,
            "total_hands": data.get("total_hands", 0),
            "win_rate": data.get("win_rate", 0),
            "profit": data.get("profit", 0),
            # Adicione mais campos conforme necessário
        }
        
        return stats
    
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar dados: {e}")
        return None

# Main
if __name__ == "__main__":
    stats = get_player_stats(name)
    if stats:
        # Criar DataFrame com pandas
        df = pd.DataFrame([stats])
        
        # Salvar em CSV
        df.to_csv("player_stats.csv", index=False)
        print("Dados salvos com sucesso.")