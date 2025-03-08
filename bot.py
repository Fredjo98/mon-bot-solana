import requests
import time
import telegram
import os
from dotenv import load_dotenv

load_dotenv()  # Charge les variables du fichier .env


# ==============================
# CONFIGURATION
# ==============================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = "-4769470702"

SOLANA_RPC_URL = "https://api.helius.xyz/v0/mainnet-rpc?api-key=ba1232d1-2f57-4cc5-a47f-1c50038a723e"

MIN_LIQUIDITY = 50000  # Liquidité minimale en $
MAX_TAX = 5  # Taxe max tolérée (%)
MAX_HOLDER_SUPPLY = 0.5  # Si un holder a +50% du supply → scam
VOLUME_PUMP_THRESHOLD = 5  # Multiplication du volume en 10 minutes pour signaler un pump

BIRDEYE_API = "https://public-api.birdeye.so/solana/v1/tokens/new"
HONEYPOT_API = "https://honeypot-api.com/check/"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/pairs/solana/"

bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
token_volumes = {}

# ==============================
# FONCTIONS
# ==============================

def get_new_tokens():
    """Récupère les nouveaux tokens listés sur Birdeye."""
    try:
        response = requests.get(BIRDEYE_API)
        if response.status_code == 200:
            return response.json().get("data", [])
    except Exception as e:
        print(f"Erreur API Birdeye : {e}")
    return []

def filter_tokens(token):
    """Filtre les tokens en fonction des critères (liquidité, taxes)."""
    liquidity = token.get("liquidity", 0)
    buy_tax = token.get("buy_tax", 0)
    sell_tax = token.get("sell_tax", 0)

    if liquidity < MIN_LIQUIDITY:
        return False
    if buy_tax > MAX_TAX or sell_tax > MAX_TAX:
        return False
    return True

def check_honeypot(token_address):
    """Vérifie si le token est un honeypot."""
    url = f"{HONEYPOT_API}{token_address}"
    try:
        response = requests.get(url)
        data = response.json()
        if data.get("is_honeypot", False):
            print(f"🚨 Honeypot détecté : {token_address}")
            return True
    except Exception as e:
        print(f"Erreur API Honeypot : {e}")
    return False

def check_holder_distribution(token_address):
    """Vérifie si un seul wallet détient +50% du supply."""
    url = f"https://api.solscan.io/account?address={token_address}"
    try:
        response = requests.get(url)
        holders = response.json().get("holders", [])
        if holders:
            top_holder = holders[0]["amount"] / sum([h["amount"] for h in holders])
            if top_holder > MAX_HOLDER_SUPPLY:
                print(f"🚨 SCAM : Un holder détient {top_holder * 100}% du supply")
                return True
    except Exception as e:
        print(f"Erreur API Holders : {e}")
    return False

def check_contract_renounced(token_address):
    """Vérifie si le contrat est renoncé (si non, risque de rugpull)."""
    url = f"https://api.dex.guru/v1/tokens/{token_address}/renounced"
    try:
        response = requests.get(url)
        data = response.json()
        if not data.get("renounced", False):
            print(f"🚨 Contrat NON renoncé pour {token_address} → Risque de rugpull")
            return False
        return True
    except Exception as e:
        print(f"Erreur API Contrat Renounced : {e}")
    return False

def check_liquidity_lock(token_address):
    """Vérifie si la liquidité est bloquée."""
    url = f"https://api.team.finance/v1/liquidity/{token_address}"
    try:
        response = requests.get(url)
        locked = response.json().get("lockedLiquidity", 0)
        if locked == 0:
            print(f"🚨 Pas de liquidity lock détecté pour {token_address}")
            return True
    except Exception as e:
        print(f"Erreur API Liquidity Lock : {e}")
    return False

def check_token_volume(token_address):
    """Vérifie l'évolution du volume d'un token et détecte un pump."""
    url = f"{DEXSCREENER_API}{token_address}"
    try:
        response = requests.get(url)
        data = response.json()
        volume_24h = data["pairs"][0]["volume"]["h24"]

        # Suivi du volume toutes les 10 minutes
        if token_address in token_volumes:
            old_volume = token_volumes[token_address]
            if volume_24h > old_volume * VOLUME_PUMP_THRESHOLD:
                print(f"🚀 PUMP DETECTÉ : {token_address} x{VOLUME_PUMP_THRESHOLD} en volume !")
                return True
        token_volumes[token_address] = volume_24h
    except Exception as e:
        print(f"Erreur API Volume : {e}")
    return False

def send_telegram_alert(token):
    """Envoie une alerte Telegram pour les bons tokens (sans scam)."""
    message = f"""
    🚀 **NOUVEAU MEMECOIN FIABLE DÉTECTÉ !** 🚀
    
    🔹 **Nom** : {token['name']}
    🔹 **Adresse** : `{token['address']}`
    🔹 **Market Cap** : {token['market_cap']}$  
    🔹 **Liquidité** : {token['liquidity']}$  
    🔹 **Buy Tax** : {token['buy_tax']}%  
    🔹 **Sell Tax** : {token['sell_tax']}%  

    📈 **Lien Birdeye** : [Voir ici](https://birdeye.so/token/{token['address']})  
    📊 **Lien DexScreener** : [Voir ici](https://dexscreener.com/solana/{token['address']})  
    """
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown", disable_web_page_preview=True)

# ==============================
# BOUCLE PRINCIPALE
# ==============================

print("🚀 Bot de détection de memecoins lancé...")

while True:
    tokens = get_new_tokens()
    
    for token in tokens:
        if filter_tokens(token):
            print(f"✅ Nouveau token détecté : {token['name']}")

            if check_honeypot(token["address"]):
                print("❌ Honeypot détecté, on ignore ce token.")
                continue

            if check_holder_distribution(token["address"]):
                print("❌ Trop de supply dans un seul wallet, on ignore ce token.")
                continue

            if not check_contract_renounced(token["address"]):
                print("❌ Contrat non renoncé, on ignore ce token.")
                continue

            if check_liquidity_lock(token["address"]):
                print("❌ Liquidité pas bloquée, on ignore ce token.")
                continue

            if check_token_volume(token["address"]):
                print("🚀 Token en pump détecté ! Envoi d'alerte...")
                send_telegram_alert(token)

    time.sleep(600)  # Vérification toutes les 10 minutes
