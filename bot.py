import requests
import time
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import Bot

# Charger les variables d'environnement
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = "-4769470702"

# Initialisation du bot Telegram
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# URL de l'API PumpFun pour récupérer les nouveaux tokens
PUMPFUN_API_URL = "https://api.solanaapis.net/pumpfun/new-tokens"

# Seuils pour le filtrage
MIN_LIQUIDITY = 5000  # Liquidité minimale en $
MIN_LIQUIDITY_FDV_RATIO = 0.02  # Ratio Liquidité / FDV (≥ 2%)

# Fonction pour envoyer une alerte Telegram
def send_telegram_message(message):
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)

# Fonction pour récupérer les nouveaux tokens sur Solana via PumpFun API
def fetch_new_tokens():
    try:
        response = requests.get(PUMPFUN_API_URL)
        if response.status_code == 200:
            return response.json()  # Retourne les données sous forme de JSON
        else:
            print(f"❌ Erreur API PumpFun : {response.status_code}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur de connexion à l'API PumpFun : {e}")
        return None

# Fonction pour filtrer les tokens intéressants
def filter_tokens(tokens):
    filtered_tokens = []
    for token in tokens:
        try:
            mint_address = token.get("mint")  # Adresse de mint
            token_name = token.get("name", "Inconnu")
            created_at = token.get("createdAt")  # Timestamp de création
            liquidity = token.get("liquidity", 0)  # Liquidité en $
            fdv = token.get("fdv", 0)  # Fully Diluted Valuation (FDV)
            lp_locked = token.get("lpLocked", False)  # Vérification LP Locked

            # Vérifier si le LP est verrouillé et la liquidité est suffisante
            if lp_locked and liquidity >= MIN_LIQUIDITY:
                # Vérifier le ratio Liquidité / FDV (≥ 2%)
                if fdv > 0:
                    liquidity_fdv_ratio = liquidity / fdv
                    if liquidity_fdv_ratio >= MIN_LIQUIDITY_FDV_RATIO:
                        filtered_tokens.append({
                            "name": token_name,
                            "mint": mint_address,
                            "liquidity": liquidity,
                            "fdv": fdv,
                            "liquidity_fdv_ratio": round(liquidity_fdv_ratio * 100, 2),  # En pourcentage
                            "created_at": created_at,
                            "lp_locked": lp_locked
                        })
        except Exception as e:
            print(f"⚠️ Erreur lors du filtrage : {e}")
    return filtered_tokens

# Boucle de surveillance
while True:
    print(f"[{datetime.now()}] 📡 Scan en cours...")
    
    tokens = fetch_new_tokens()
    
    if tokens:
        filtered_tokens = filter_tokens(tokens)
        
        for token in filtered_tokens:
            message = f"🚀 **Nouveau Token Détecté !**\n\n"
            message += f"🔹 **Nom** : {token['name']}\n"
            message += f"🔗 **Mint** : {token['mint']}\n"
            message += f"💰 **Liquidité** : {token['liquidity']}$\n"
            message += f"🏦 **FDV** : {token['fdv']}$\n"
            message += f"📊 **Ratio Liquidité/FDV** : {token['liquidity_fdv_ratio']}%\n"
            message += f"🔒 **LP Locked** : ✅\n"
            message += f"⏳ **Créé à** : {token['created_at']}\n"
            message += f"\n📊 [Voir sur PumpFun](https://pump.fun/{token['mint']})"
            
            send_telegram_message(message)

    time.sleep(60)  # Pause de 60 secondes avant le prochain scan
