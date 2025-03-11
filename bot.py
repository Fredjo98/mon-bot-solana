import requests
import time
import telegram
import os
from dotenv import load_dotenv

# Charger les variables du fichier .env
load_dotenv()

# ==============================
# CONFIGURATION
# ==============================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("🚨 ERREUR : La variable TELEGRAM_BOT_TOKEN est vide ou non définie !")

TELEGRAM_CHAT_ID = "-4769470702"

SOLANA_RPC_URL = "https://api.helius.xyz/v0/mainnet-rpc?api-key=ba1232d1-2f57-4cc5-a47f-1c50038a723e"

MIN_LIQUIDITY = 50000  # Liquidité minimale en $
MAX_TAX = 5  # Taxe max tolérée (%)
MAX_HOLDER_SUPPLY = 0.5  # Si un holder a +50% du supply → scam
VOLUME_PUMP_THRESHOLD = 5  # Multiplication du volume en 10 minutes pour signaler un pump

JUPITER_API = "https://quote-api.jup.ag/v6/tokens"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/search?q=solana"


bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
token_volumes = {}

# ==============================
# FONCTIONS
# ==============================

def check_honeypot(token_address):
    """Vérifie si le token est un honeypot en regardant son historique de transactions."""
    url = f"https://pro-api.solscan.io/v1/token/transactions?tokenAddress={token_address}&limit=20"
    
    headers = {"accept": "application/json"}  # Solscan ne nécessite pas de clé API

    try:
        response = requests.get(url, headers=headers)
        data = response.json()

        # Filtrer les types de transactions
        buy_count = sum(1 for tx in data.get("data", []) if "transfer" in tx["txType"])
        sell_count = sum(1 for tx in data.get("data", []) if "burn" in tx["txType"])

        if sell_count == 0 and buy_count > 5:
            print(f"🚨 POSSIBLE HONEYPOT : {token_address} (Achat uniquement, aucune vente détectée)")
            return True  # Honeypot détecté
        return False  # OK
    except Exception as e:
        print(f"Erreur API Solscan pour honeypot check : {e}")
        return False


def check_holder_distribution(token_address):
    """Vérifie si un holder détient +50% du supply en utilisant Solana RPC."""
    
    url = SOLANA_RPC_URL  # Ton RPC Helius ou autre
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenLargestAccounts",
        "params": [token_address]
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()

        if "result" in data and "value" in data["result"]:
            holders = data["result"]["value"]
            total_supply = sum(int(holder["uiAmount"]) for holder in holders)

            if total_supply > 0:
                top_holder_percentage = (int(holders[0]["uiAmount"]) / total_supply) * 100

                if top_holder_percentage > MAX_HOLDER_SUPPLY * 100:
                    print(f"🚨 SCAM : Un holder détient {top_holder_percentage:.2f}% du supply")
                    return True  # SCAM détecté

        return False  # OK
    except Exception as e:
        print(f"Erreur API Solana RPC pour check holder distribution : {e}")
        return False


def check_contract_renounced(token_address):
    """Vérifie si le contrat est renoncé en utilisant Solana RPC."""
    
    url = SOLANA_RPC_URL  # Ton RPC Helius ou autre
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [token_address, {"encoding": "jsonParsed"}]
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        data = response.json()

        if "result" in data and "value" in data["result"]:
            account_info = data["result"]["value"]
            
            # Vérifier si le champ "owner" est "11111111111111111111111111111111" (adresse nulle)
            if account_info["owner"] == "11111111111111111111111111111111":
                print(f"✅ Contrat renoncé pour {token_address}")
                return True  # Contrat bien renoncé
            else:
                print(f"🚨 Contrat NON renoncé pour {token_address} → Risque de rugpull")
                return False  # Contrat non renoncé

        return False  # Problème avec la requête RPC
    except Exception as e:
        print(f"Erreur API Solana RPC pour check contract renounced : {e}")
        return False


def check_liquidity_lock(token_address):
    """Vérifie si la liquidité est bloquée en analysant la pool sur Raydium."""
    
    url = f"{DEXSCREENER_API}{token_address}"
    
    try:
        response = requests.get(url)
        data = response.json()

        if "pairs" in data and len(data["pairs"]) > 0:
            pool_info = data["pairs"][0]
            liquidity = pool_info.get("liquidity", {}).get("usd", 0)
            lp_holders = pool_info.get("lp_holders", [])

            print(f"💧 Liquidité trouvée : {liquidity}$")
            
            # Vérifier si les LP tokens sont détenus par un locker
            locked = any("locker" in holder["address"].lower() for holder in lp_holders)

            if locked:
                print(f"✅ Liquidité bloquée pour {token_address}")
                return True
            else:
                print(f"🚨 Alerte ! Liquidité NON bloquée pour {token_address}")
                return False

    except Exception as e:
        print(f"Erreur API Dexscreener pour check liquidity lock : {e}")
    
    return False


def check_token_volume(pair_id):
    """Vérifie l'évolution du volume d'un token et détecte un pump."""
    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_id}"

    try:
        response = requests.get(url)
        
        if response.status_code != 200:
            print(f"❌ Erreur API Volume DexScreener : {response.status_code} - {response.text}")
            return False

        data = response.json()
        
        if "pairs" not in data or not data["pairs"]:
            print(f"⚠️ Aucun volume trouvé pour {pair_id} sur DexScreener.")
            return False

        volume_24h = data["pairs"][0]["volume"]["h24"]

        # Suivi du volume toutes les 10 minutes
        if pair_id in token_volumes:
            old_volume = token_volumes[pair_id]
            if volume_24h > old_volume * VOLUME_PUMP_THRESHOLD:
                print(f"🚀 PUMP DETECTÉ : {pair_id} x{VOLUME_PUMP_THRESHOLD} en volume !")
                return True

        token_volumes[pair_id] = volume_24h

    except Exception as e:
        print(f"Erreur API Volume DexScreener : {e}")

    return False


import requests

def get_new_tokens():
    """Récupère les nouvelles paires de trading sur Solana via DexScreener."""
    
    url = "https://api.dexscreener.com/latest/dex/pairs/solana"
    
    try:
        response = requests.get(url)
        print(f"📢 Debug : Réponse API - {response.status_code}")  # Vérifier la réponse

        if response.status_code != 200:
            print(f"❌ Erreur API DexScreener : {response.status_code} - {response.text}")
            return []

        data = response.json()
        print(f"📢 Debug : Contenu API - {data}")  # Voir le contenu

        if "pairs" not in data or not data["pairs"]:
            print("⚠️ Aucun token trouvé dans la réponse DexScreener.")
            return []

        tokens = []
        excluded_symbols = {"SOL", "SOLANA"}  # Exclure les jetons non pertinents

        for pair in data["pairs"]:
            if pair["chainId"] != "solana":
                continue  # On garde seulement les tokens Solana
            
            symbol = pair["baseToken"]["symbol"]
            if symbol in excluded_symbols:
                continue  # Ignorer SOL et SOLANA

            tokens.append({
                "symbol": symbol,
                "address": pair["baseToken"]["address"],
                "liquidity": pair.get("liquidity", {}).get("usd", 0),
                "market_cap": pair.get("fdv", 0),
                "pair_id": pair["pairAddress"]
            })

        print(f"📢 Debug : Tokens détectés - {tokens}")  # Vérifier si des tokens sont récupérés
        return tokens

    except Exception as e:
        print(f"❌ Erreur API DexScreener : {e}")
        return []








def filter_tokens(token):
    """Filtre les tokens selon les critères (liquidité, taxes)."""
    liquidity = token.get("liquidity", 0)
    buy_tax = token.get("buy_tax", 0)
    sell_tax = token.get("sell_tax", 0)

    if liquidity < MIN_LIQUIDITY:
        return False
    if buy_tax > MAX_TAX or sell_tax > MAX_TAX:
        return False
    return True

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

    📈 **Lien Jupiter** : [Acheter ici](https://jup.ag/swap/SOL-{token['address']})  
    📊 **Lien DexScreener** : [Voir ici](https://dexscreener.com/solana/{token['address']})  
    """
    bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown", disable_web_page_preview=True)

# ==============================
# BOUCLE PRINCIPALE
# ==============================

print("🚀 Bot de détection de memecoins lancé...")

while True:
    tokens = get_new_tokens()  # 🔹 Récupération des nouveaux tokens via DexScreener

    for token in tokens:
        print(f"📢 Debug : token brut → {token}")  # Voir ce qui est reçu
        print(f"✅ Nouveau token détecté : {token['symbol']} - {token['address']}")

        if check_honeypot(token["address"]):  # Vérifier si c'est un honeypot
            continue
        if check_holder_distribution(token["address"]):  # Vérifier si un holder détient +50%
            continue
        if not check_contract_renounced(token["address"]):  # Vérifier si le contrat est renoncé
            continue
        if not check_liquidity_lock(token["address"]):  # Vérifier si la liquidité est bloquée
            continue
        if check_token_volume(token["pair_id"]):  # 🔹 Utilisation du pair_id pour vérifier le volume
            send_telegram_alert(token)  # Envoi d'une alerte Telegram

    time.sleep(600)  # Pause de 10 minutes


