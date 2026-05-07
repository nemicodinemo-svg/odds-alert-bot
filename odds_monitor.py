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

# 🎯 WHITELIST CAMPIONATI TESTATI (funzionano con free tier + mercati BTTS/Over)
ALLOWED_LEAGUES = [
    "soccer_epl",                    # Premier League
    "soccer_italy_seriea",           # Serie A
    "soccer_spain_la_liga",          # La Liga
    "soccer_germany_bundesliga",     # Bundesliga
    "soccer_france_ligue_one",       # Ligue 1
    "soccer_uefa_champs_league",     # Champions League
    "soccer_uefa_europa_league",     # Europa League
    "soccer_netherlands_eredivisie", # Eredivisie
    "soccer_portugal_primeira_liga", # Primeira Liga
    "soccer_england_league1",        # League 1 (se vuoi più partite)
]

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

def fetch_and_check():
    alerts = []
    state = load_state()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=24)
    first_run = len(state) == 0
    
    logging.info(f"🔍 Controllo {len(ALLOWED_LEAGUES)} campionati whitelist...")
    all_matches = []

    for league in ALLOWED_LEAGUES:
        try:
            url = f"{BASE_URL}/sports/{league}/odds/"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "eu",
                "markets": "totals,both_teams_to_score",
                "oddsFormat": "decimal"
            }
            res = requests.get(url, params=params, timeout=15)
            
            if res.status_code == 429:
                logging.warning("⚠️ Rate limit API raggiunto.")
                break
            elif res.status_code == 422:
                logging.warning(f"⚠️ {league}: mercato non disponibile, salto.")
                continue
                
            res.raise_for_status()
            data = res.json()
            if isinstance(data, list):
                all_matches.extend(data)
                logging.info(f"✅ {league}: {len(data)} partite trovate")
                
        except Exception as e:
            logging.error(f"❌ Errore {league}: {e}")
            continue

    if not all_matches:
        logging.warning("⚠️ Nessuna partita trovata con quote Bet365.")
        return

    for m in all_matches:
        try:
            commence = datetime.fromisoformat(m["commence_time"].replace("Z", "+00:00"))
        except: 
            continue
        
        if commence < now or commence > cutoff: 
            continue

        bk = next((b for b in m.get("bookmakers", []) if b["key"] == BOOKMAKER), None)
        if not bk: 
            continue

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
                                alerts.append(f" <b>BTTS Sì</b>\n{m['home_team']} vs {m['away_team']}\n{BOOKMAKER.upper()}: {old:.2f} → {price:.2f} ({drop:.1f}%↓)")
                        state[key] = price

    # Pulizia stato: tieni solo partite ancora valide
    valid_ids = {m["id"] for m in all_matches}
    state = {k: v for k, v in state.items() if k.split("_")[0] in valid_ids}

    if alerts:
        send_telegram("🚨 <b>ALERT VARIAZIONE QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
    else:
        logging.info(f"ℹ️ Nessuna variazione >= {MIN_DROP_PERCENT}% rilevata su {len(all_matches)} partite.")
    
    save_state(state)
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    logging.info("🟢 Avvio monitoraggio...")
    fetch_and_check()
