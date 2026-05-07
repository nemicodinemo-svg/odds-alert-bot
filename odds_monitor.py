import requests, json, os, logging
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
API_KEY = os.getenv("API_FOOTBALL_KEY")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
MIN_DROP_PERCENT = 10  # Soglia drop (%)
STATE_FILE = "odds_state.json"

logging.basicConfig(filename="odds_monitor.log", level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", filemode="a")

def load_state():
    try:
        with open(STATE_FILE, "r") as f: return json.load(f)
    except: return {}

def save_state(data):
    with open(STATE_FILE, "w") as f: json.dump(data, f, indent=2)

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"})
        logging.info(f"Telegram sent: {r.status_code}")
    except Exception as e: logging.error(f"Telegram Error: {e}")

def run():
    logging.info("🟢 Avvio Bot API-Football...")
    
    if not API_KEY:
        logging.error("❌ API Key mancante!")
        return

    headers = {"x-apisports-key": API_KEY}
    base_url = "https://v3.football.api-sports.io"
    
    # Date da controllare (Oggi e Domani)
    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    dates = [today, tomorrow]
    
    state = load_state()
    first_run = len(state) == 0
    alerts = []
    
    for date in dates:
        try:
            # Richiesta ODDS per Bet365 (ID 8)
            params = {"date": date, "bookmaker": "8"} 
            res = requests.get(f"{base_url}/odds", headers=headers, params=params, timeout=20)
            
            if res.status_code != 200:
                logging.error(f"Errore API {date}: {res.text}")
                continue
                
            data = res.json()
            if data.get("response"):
                logging.info(f"✅ Trovate {len(data['response'])} partite per il {date}")
                
                for match_data in data["response"]:
                    # CORREZIONE QUI: teams è a livello root, non dentro fixture
                    try:
                        home = match_data["teams"]["home"]["name"]
                        away = match_data["teams"]["away"]["name"]
                        fixture_id = match_data["fixture"]["id"]
                        league = match_data["league"]["name"]
                    except KeyError:
                        continue # Salta se mancano dati essenziali
                        
                    # Cerca Bet365 nei bookmakers
                    bk_365 = None
                    for bk in match_data.get("bookmakers", []):
                        if bk["id"] == 8: # 8 è l'ID di Bet365
                            bk_365 = bk
                            break
                    
                    if not bk_365: continue

                    # Controlla mercati
                    for bet in bk_365.get("bets", []):
                        # Bet 5 = BTTS, Bet 8 = Goals Over/Under
                        if bet["id"] in [5, 8]: 
                            for val in bet.get("values", []):
                                target_val = None
                                if bet["id"] == 5 and val["value"] == "Yes": target_val = "BTTS Sì"
                                if bet["id"] == 8 and val["value"] == "Over 2.5": target_val = "Over 2.5"
                                
                                if target_val:
                                    try:
                                        price = float(val["odd"])
                                        key = f"{fixture_id}_{target_val}"
                                        
                                        if key in state:
                                            old_price = state[key]
                                            # Calcolo Drop
                                            if old_price > price:
                                                drop = ((old_price - price) / old_price) * 100
                                                if drop >= MIN_DROP_PERCENT:
                                                    alerts.append(f"📉 <b>{target_val}</b>\n{home} vs {away}\n({league})\nQuota: {old_price} ➔ {price}\nDrop: {drop:.1f}%")
                                        
                                        # Aggiorna stato con nuovo prezzo
                                        state[key] = price
                                    except: continue
        except Exception as e:
            logging.error(f"Errore critico {date}: {e}")

    save_state(state)
    
    if alerts:
        msg = " <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts)
        send_telegram(msg)
    else:
        logging.info("Nessun alert significativo.")

if __name__ == "__main__":
    run()
