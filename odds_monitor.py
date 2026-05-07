import requests, json, os, logging
from datetime import datetime, timezone, timedelta

# 🔑 CONFIGURAZIONE
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
MIN_DROP_PERCENT = 12
BOOKMAKER = "bet365"
STATE_FILE = "odds_state.json"
LOG_FILE = "odds_monitor.log"

BASE_URL = "https://api.the-odds-api.com/v4"
SPORT_FILTER = "soccer_"
MAX_LEAGUES = 12

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", filemode="a")

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def send_telegram(text):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        logging.error("Credenziali Telegram mancanti!")
        return
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        logging.info("✅ Alert inviato")
    except Exception as e:
        logging.error(f"❌ Errore Telegram: {e}")

def get_active_leagues():
    try:
        if not ODDS_API_KEY:
            logging.error("API Key mancante!")
            return []
        res = requests.get(f"{BASE_URL}/sports/", params={"apiKey": ODDS_API_KEY}, timeout=10)
        res.raise_for_status()
        data = res.json()
        if not isinstance(data, list): return []
        return [s["key"] for s in data if s["key"].startswith(SPORT_FILTER)][:MAX_LEAGUES]
    except Exception as e:
        logging.error(f"Errore campionati: {e}")
        return []

def fetch_and_check():
    alerts = []
    state = load_state()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    first_run = len(state) == 0
    
    leagues = get_active_leagues()
    if not leagues:
        logging.warning("Nessun campionato trovato.")
        return

    all_matches = []
    logging.info(f"🔍 Controllo {len(leagues)} campionati...")

    for league in leagues:
        try:
            res = requests.get(f"{BASE_URL}/sports/{league}/odds/", params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "totals,both_teams_to_score", "oddsFormat": "decimal"}, timeout=15)
            if res.status_code == 429: 
                logging.warning("⚠️ Rate limit raggiunto.")
                break
            res.raise_for_status()
            data = res.json()
            if isinstance(data, list):
                all_matches.extend(data)
        except Exception as e:
            logging.error(f"Errore {league}: {e}")
            continue

    for m in all_matches:
        try:
            commence = datetime.fromisoformat(m["commence_time"].replace("Z", "+00:00"))
        except: continue
        
        if commence < now or commence > cutoff: continue

        bk = next((b for b in m.get("bookmakers", []) if b["key"] == BOOKMAKER), None)
        if not bk: continue

        for mk in bk["markets"]:
            if mk["key"] == "totals":
                for o in mk["outcomes"]:
                    if o["name"] == "Over":
                        key = f"{m['id']}_tot_Over"
                        old = state.get(key)
                        price = o["price"]
                        if old and old > 0 and not first_run:
                            drop = ((old - price) / old) * 100
                            if drop >= MIN_DROP_PERCENT:
                                alerts.append(f"📉 <b>Over 2.5</b>\n{m['home_team']} vs {m['away_team']}\n{BOOKMAKER.upper()}: {old:.2f} → {price:.2f} ({drop:.1f}%↓)")
                        state[key] = price
            elif mk["key"] == "both_teams_to_score":
                for o in mk["outcomes"]:
                    if o["name"] == "Yes":
                        key = f"{m['id']}_btts_Yes"
                        old = state.get(key)
                        price = o["price"]
                        if old and old > 0 and not first_run:
                            drop = ((old - price) / old) * 100
                            if drop >= MIN_DROP_PERCENT:
                                alerts.append(f"📉 <b>BTTS Sì</b>\n{m['home_team']} vs {m['away_team']}\n{BOOKMAKER.upper()}: {old:.2f} → {price:.2f} ({drop:.1f}%↓)")
                        state[key] = price

    valid_ids = {m["id"] for m in all_matches}
    state = {k: v for k, v in state.items() if k.split("_")[0] in valid_ids}

    if alerts:
        send_telegram("🚨 <b>ALERT VARIAZIONE QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
    
    save_state(state)
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    logging.info("🟢 Avvio monitoraggio...")
    fetch_and_check()
