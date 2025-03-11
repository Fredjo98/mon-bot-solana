import requests
import time
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import Bot

# Charger la variable depuis .env
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Définir le Chat ID directement dans le code
TELEGRAM_CHAT_ID = "-4769470702"  # Mets ton vrai chat ID ici

# Vérifier que le token est bien chargé
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("🚨 Erreur : Vérifie ton fichier .env et assure-toi que TELEGRAM_BOT_TOKEN est bien défini !")

# Configurer le bot Telegram
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# API Dexscreener
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens"
CHAIN = "solana"
SCAN_INTERVAL = 60  # Temps entre chaque scan (en secondes)

# Fonction pour vérifier si un token est un bon memecoin
def is_potential_memecoin(token):
    memecoin_keywords = ["dog", "pepe", "inu", "shiba", "elon", "meme", "woof", "pup"]
    name = token.get("baseToken", {}).get("name", "").lower()
    symbol = token.get("baseToken", {}).get("symbol", "").lower()

    # Vérifie si le token a un nom de memecoin
    if not any(word in name or word in symbol for word in memecoin_keywords):
        return False

    # Vérifie la liquidité (évite les rug pulls)
    liquidity = float(token.get("pair", {}).get("liquidity", {}).get("usd", 0))
    if liquidity < 5000:
        return False

    # Vérifie le volume d’échange
    volume_1h = float(token.get("pair", {}).get("volume", {}).get("h1", {}).get("usd", 0))
    volume_24h = float(token.get("pair", {}).get("volume", {}).get("h24", {}).get("usd", 0))
    if volume_1h < 1000 or volume_24h < 5000:
        return False

    # Vérifie le market cap (on cherche un low cap < 1M$)
    fdv = float(token.get("pair", {}).get("fdv", 0))
    if fdv > 1000000 or fdv == 0:
        return False

    # Vérifie la tendance de prix sur 1h
    price_change_1h = float(token.get("pair", {}).get("priceChange", {}).get("h1", 0))
    if price_change_1h < -20:
        return False

    # 🔒 Vérifie le ratio Liquidité / FDV (Liquidité ≥ 2% du FDV)
    lp_ratio = (liquidity / fdv) * 100 if fdv > 0 else 0
    if lp_ratio < 2:
        return False  # LP trop faible, risque de rug pull

    return True

# Fonction principale pour scanner les memecoins
def scan_for_memecoins():
    print(f"[{datetime.now()}] 📡 Scan en cours...")

    response = requests.get(DEXSCREENER_API)
    if response.status_code != 200:
        print("❌ Erreur API Dexscreener !")
        return
    
    data = response.json()
    tokens = data.get("pairs", [])

    found_memecoins = []

    for token in tokens:
        if token.get("chainId") == CHAIN and is_potential_memecoin(token):
            found_memecoins.append(token)

    if found_memecoins:
        print(f"✅ {len(found_memecoins)} memecoins trouvés sur Solana !")

        message = "🚀 **Nouveaux Memecoins sur Solana !** 🚀\n\n"
        for t in found_memecoins:
            name = t.get("baseToken", {}).get("name", "Inconnu")
            symbol = t.get("baseToken", {}).get("symbol", "???")
            price = float(t.get("priceUsd", 0))
            dex_url = t.get("url", "")
            liquidity = float(t.get("pair", {}).get("liquidity", {}).get("usd", 0))
            fdv = float(t.get("pair", {}).get("fdv", 0))
            lp_ratio = (liquidity / fdv) * 100 if fdv > 0 else 0

            message += f"🔹 {name} ({symbol})\n"
            message += f"💰 Prix : ${price:.6f}\n"
            message += f"💧 Liquidité : ${liquidity:,.0f}\n"
            message += f"🏛️ FDV : ${fdv:,.0f}\n"
            message += f"🔒 LP Ratio : {lp_ratio:.2f}%\n"
            message += f"🔗 [Dexscreener]({dex_url})\n\n"

        # Envoyer le message sur Telegram
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown")

    else:
        print("❌ Aucun bon memecoin trouvé...")

# Lancer le script en boucle
if __name__ == "__main__":
    while True:
        scan_for_memecoins()
        time.sleep(SCAN_INTERVAL)