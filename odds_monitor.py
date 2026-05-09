import requests, json, os, logging
from datetime import datetime, timedelta

API_KEY = os.getenv("API_FOOTBALL_KEY")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
STATE_FILE = "odds_state.json"

logging.basicConfig(filename="odds_monitor.log", level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", filemode="a")

def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_state(data):
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        logging.info(f"Telegram: {r.status_code}")
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

def utc_to_italy(utc_str):
    try:
        clean_str = utc_str.replace('Z', '+00:00')
        utc_time = datetime.fromisoformat(clean_str)
        italy_time = utc_time + timedelta(hours=2)
        return italy_time.strftime("%d/%m %H:%M")
    except:
        return utc_str[:16]

def fetch_teams_cache(dates, headers, base_url):
    cache = {}
    for date in dates:
        try:
            res = requests.get(f"{base_url}/fixtures", headers=headers, params={"date": date}, timeout=10)
            if res.status_code == 200:
                for fix in res.json().get("response", []):
                    fid = fix["fixture"]["id"]
                    cache[fid] = {
                        "home": fix["teams"]["home"]["name"],
                        "away": fix["teams"]["away"]["name"],
                        "league": fix["league"]["name"]
                    }
        except:
            pass
    return cache

def run():
    logging.info("🟢 Avvio Bot...")
    if not API_KEY:
        logging.error("❌ API Key mancante!")
        return

    headers = {"x-apisports-key": API_KEY}
    base_url = "https://v3.football.api-sports.io"

    # 🕐 Calcolo date in orario italiano (GitHub usa UTC, noi aggiungiamo +2h)
    now_italy = datetime.utcnow() + timedelta(hours=2)
    today = now_italy.strftime("%Y-%m-%d")
    tomorrow = (now_italy + timedelta(days=1)).strftime("%Y-%m-%d")
    dates = [today, tomorrow]

    teams_cache = fetch_teams_cache(dates, headers, base_url)
    logging.info(f"📦 Cache squadre: {len(teams_cache)} partite")

    state = load_state()
    first_run = len(state) == 0
    alerts = []
    processed = 0

    for date in dates:
        try:
            res = requests.get(f"{base_url}/odds", headers=headers, params={"date": date, "bookmaker": "8"}, timeout=15)
            
            if res.status_code == 429:
                logging.warning("⏳ Rate limit!")
                break
            if res.status_code != 200:
                continue

            data = res.json()
            matches = data.get("response", [])
            if not matches:
                continue

            logging.info(f"✅ {date}: {len(matches)} partite con quote Bet365")

            for m in matches:
                try:
                    fid = m.get("fixture", {}).get("id")
                    if not fid or fid not in teams_cache:
                        continue
                    
                    home = teams_cache[fid]["home"]
                    away = teams_cache[fid]["away"]
                    league = teams_cache[fid]["league"]
                    fixture_date = m.get("fixture", {}).get("date", "")
                    italy_time = utc_to_italy(fixture_date)

                    bk = next((b for b in m.get("bookmakers", []) if b.get("id") == 8), None)
                    if not bk:
                        continue

                    for bet in bk.get("bets", []):
                        if bet.get("id") in [1, 5, 8]:
                            for v in bet.get("values", []):
                                try:
                                    price = float(v.get("odd"))
                                    key = f"{fid}_{bet['id']}_{v['value'].replace(' ', '_')}"
                                    old = state.get(key)

                                    if old and old > 0 and not first_run:
                                        drop = ((old - price) / old) * 100
                                        if drop >= 10:
                                            alerts.append(f" <b>{v['value']}</b>\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({drop:.1f}%↓)\n {italy_time}")

                                    state[key] = price
                                    processed += 1
                                except ValueError:
                                    continue
                except Exception as e:
                    logging.error(f" Errore processing: {e}")

        except Exception as e:
            logging.error(f"❌ Errore critico {date}: {e}")

    save_state(state)
    
    if alerts:
        send_telegram("🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
        logging.info(f" Inviati {len(alerts)} alert")
    else:
        logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
    
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    run()
