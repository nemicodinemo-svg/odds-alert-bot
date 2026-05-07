import requests, json, os, logging
from datetime import datetime, timezone, timedelta

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
    return json.load(open(STATE_FILE, "r", encoding="utf-8")) if os.path.exists(STATE_FILE) else {}

def save_state(state):
    json.dump(state, open(STATE_FILE, "w", encoding="utf-8"), indent=2)

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"}, timeout=10)
        r.raise_for_status()
        logging.info("✅ Alert inviato")
    except Exception as e:
        logging.error(f"❌ Errore Telegram: {e}")

def get_active_leagues():
    try:
        res = requests.get(f"{BASE_URL}/sports/", params={"apiKey": ODDS_API_KEY}, timeout=10)
        res.raise_for_status()
        return [s["key"] for s in res.json() if s["key"].startswith(SPORT_FILTER)][:MAX_LEAGUES]
    except: return []

def fetch_and_check():
    alerts, state = [], load_state()
    now, cutoff = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(hours=24)
    first_run = len(state) == 0
    leagues = get_active_leagues()
    if not leagues: return

    for league in leagues:
        try:
            res = requests.get(f"{BASE_URL}/sports/{league}/odds/", params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "totals,both_teams_to_score", "oddsFormat": "decimal"}, timeout=15)
            if res.status_code == 429: break
            res.raise_for_status()
        except: continue

        for m in res.json():
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
                            if old and old > 0 and not first_run:
                                drop = ((old - o["price"]) / old) * 100
                                if drop >= MIN_DROP_PERCENT:
                                    alerts.append(f"📉 <b>Over 2.5</b>\n{m['home_team']} vs {m['away_team']}\n{BOOKMAKER.upper()}: {old:.2f} → {o['price']:.2f} ({drop:.1f}%↓)")
                            state[key] = o["price"]
                elif mk["key"] == "both_teams_to_score":
                    for o in mk["outcomes"]:
                        if o["name"] == "Yes":
                            key = f"{m['id']}_btts_Yes"
                            old = state.get(key)
                            if old and old > 0 and not first_run:
                                drop = ((old - o["price"]) / old) * 100
                                if drop >= MIN_DROP_PERCENT:
                                    alerts.append(f" <b>BTTS Sì</b>\n{m['home_team']} vs {m['away_team']}\n{BOOKMAKER.upper()}: {old:.2f} → {o['price']:.2f} ({drop:.1f}%↓)")
                            state[key] = o["price"]

    valid = {s.split("_")[0] for s in state.keys()} & {m["id"] for m in res.json()}
    state = {k: v for k, v in state.items() if k.split("_")[0] in valid}

    if alerts:
        send_telegram("🚨 <b>ALERT VARIAZIONE QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
    save_state(state)
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    fetch_and_check()
