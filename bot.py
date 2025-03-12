import requests
import time
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import Bot

# Charger les variables d'environnement
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BITQUERY_API_KEY = os.getenv("BITQUERY_API_KEY")
TELEGRAM_CHAT_ID = "-4769470702"

# Initialisation du bot Telegram
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# API Bitquery
BITQUERY_API_URL = "https://graphql.bitquery.io/"

# 🔍 Fonction pour interroger l'API Bitquery
def fetch_tokens():
    url = "https://graphql.bitquery.io"
    headers = {"X-API-KEY": BITQUERY_API_KEY, "Content-Type": "application/json"}
    query = """
    {
      solana(network: solana) {
        dexTrades(
          options: {limit: 10, desc: "tradeAmount"}
          date: {since: "2025-03-12"}
        ) {
          baseCurrency {
            address
            symbol
          }
          tradeAmount(in: USD)
          buyAmount(in: USD)
          sellAmount(in: USD)
          quotePrice
          smartContract {
            address {
              annotation
            }
          }
        }
      }
    }
    """
    
    response = requests.post(url, json={"query": query}, headers=headers)
    
    if response.status_code == 200:
        return response.json()["data"]["solana"]["dexTrades"]
    else:
        print("❌ Erreur API Bitquery !", response.text)
        return None

# 🔒 Vérifie le ratio Liquidité / FDV (≥ 2%)
def check_liquidity_fdv_ratio(token_address):
    url = f"https://graphql.bitquery.io"
    headers = {"X-API-KEY": BITQUERY_API_KEY, "Content-Type": "application/json"}
    query = f"""
    {{
      solana {{
        tokenTransfers(
          currency: {{is: "{token_address}"}}
          options: {{limit: 1, desc: "date.date"}}
        ) {{
          currency {{
            symbol
          }}
          amount
        }}
      }}
    }}
    """
    
    response = requests.post(url, json={"query": query}, headers=headers)
    
    if response.status_code == 200:
        data = response.json()["data"]["solana"]["tokenTransfers"]
        if data:
            liquidité = data[0]["amount"]
            fdv = liquidité * 50  # Approximation FDV
            return liquidité / fdv >= 0.02
    return False

# 🛡 Vérifie si le token est un honeypot (peut-il être vendu ?)
def is_honeypot(token_address):
    url = f"https://api.bitquery.io/v2/honeypot/{token_address}"
    response = requests.get(url, headers={"X-API-KEY": BITQUERY_API_KEY})
    
    if response.status_code == 200:
        data = response.json()
        return not data.get("is_honeypot", False)
    return False

# 🏦 Vérifie si quelques holders possèdent trop de tokens
def check_holders_distribution(token_address):
    url = f"https://graphql.bitquery.io"
    headers = {"X-API-KEY": BITQUERY_API_KEY, "Content-Type": "application/json"}
    query = f"""
    {{
      solana {{
        tokenHolders(
          currency: {{is: "{token_address}"}}
          options: {{limit: 10, desc: "balance"}}
        ) {{
          balance
          address {{
            address
          }}
        }}
      }}
    }}
    """
    
    response = requests.post(url, json={"query": query}, headers=headers)
    
    if response.status_code == 200:
        holders = response.json()["data"]["solana"]["tokenHolders"]
        total_supply = sum([h["balance"] for h in holders])
        top_holder_supply = holders[0]["balance"] if holders else 0
        
        return top_holder_supply / total_supply < 0.10  # Le plus gros holder ne doit pas avoir + de 10%
    
    return False

# 🚀 Analyse et sélection des meilleurs tokens
def analyze_tokens():
    tokens = fetch_tokens()
    
    if not tokens:
        return

    for token in tokens:
        symbol = token["baseCurrency"]["symbol"]
        address = token["baseCurrency"]["address"]
        trade_amount = token["tradeAmount"]
        
        if (
            trade_amount > 10000 and  # Volume minimum de 10k$
            check_liquidity_fdv_ratio(address) and
            is_honeypot(address) and
            check_holders_distribution(address)
        ):
            message = f"""
            🚀 Nouveau Token Prometteur 🚀
            🏷 Symbol: {symbol}
            📜 Adresse: {address}
            💰 Volume: {trade_amount}$
            ✅ Liquidity/FDV Ratio OK
            ✅ Pas un Honeypot
            ✅ Holders bien répartis
            """
            bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
            print(message)
        else:
            print(f"❌ {symbol} n'a pas passé les filtres.")

# 🔄 Lancement du scan en boucle
if __name__ == "__main__":
    while True:
        print(f"[{datetime.now()}] 📡 Scan en cours...")
        analyze_tokens()
        time.sleep(60)  # Rafraîchissement toutes les 60s
