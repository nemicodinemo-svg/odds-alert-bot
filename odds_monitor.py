import requests, json, os, logging, sys
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
PROXY_URL = os.getenv("PROXY_URL")  # URL del Cloudflare Worker
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
STATE_FILE = "odds_state.json"

# Logging FILE + CONSOLE
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("odds_monitor.log", mode="a"),
        logging.StreamHandler(sys.stdout)
    ]
)

def load_state():
    try:
        with open(STATE_FILE, "r") as f: return json.load(f)
    except: return {}

def save_state(data):
    with open(STATE_FILE, "w") as f: json.dump(data, f, indent=2)

def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        logging.info(f"Telegram: {r.status_code}")
    except Exception as e: logging.error(f"Telegram Error: {e}")

def utc_to_italy(utc_str):
    try:
        utc_time = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        return (utc_time + timedelta(hours=2)).strftime("%d/%m %H:%M")
    except: return utc_str[:16]

def run():
    logging.info("🟢 Avvio Bot (Proxy Mode)...")
    if not PROXY_URL:
        logging.error("❌ PROXY_URL mancante!")
        return

    try:
        # 📥 Scarica dati dal Proxy (NON chiama direttamente le API!)
        logging.info(f"📡 Richiesta dati a: {PROXY_URL}")
        res = requests.get(PROXY_URL, timeout=15)
        
        if res.status_code != 200:
            logging.error(f"❌ Errore Proxy: {res.status_code}")
            return
        
        data = res.json()
        football_data = data.get("football", {}).get("response", [])
        
        logging.info(f"✅ Ricevute {len(football_data)} partite dal proxy")
        
        # 🔄 Elabora le partite (stessa logica di prima)
        state = load_state()
        first_run = len(state) == 0
        alerts = []
        processed = 0

        for match in football_data:
            try:
                fid = match.get("fixture", {}).get("id")
                home = match.get("teams", {}).get("home", {}).get("name", "Unknown")
                away = match.get("teams", {}).get("away", {}).get("name", "Unknown")
                league = match.get("league", {}).get("name", "Unknown")
                fixture_date = match.get("fixture", {}).get("date", "")
                italy_time = utc_to_italy(fixture_date)
                
                # Qui potresti aggiungere la logica per estrarre le quote dal proxy
                # Per ora è un esempio base
                
            except Exception as e:
                logging.error(f"⚠️ Errore processing: {e}")

        save_state(state)
        
        if alerts:
            send_telegram("🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
            logging.info(f"🚨 Inviati {len(alerts)} alert")
        else:
            logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
        
        logging.info("🔄 Ciclo completato.")

    except Exception as e:
        logging.error(f"❌ Errore critico: {e}")

if __name__ == "__main__":
    run()
