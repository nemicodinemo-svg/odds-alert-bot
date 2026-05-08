import requests, json, os, logging
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
API_KEY = os.getenv("API_FOOTBALL_KEY")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
STATE_FILE = "odds_state.json"

logging.basicConfig(filename="odds_monitor.log", level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s", filemode="a")

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

def run():
    logging.info("🟢 Avvio Bot (Fix Estrazione Squadre)...")
    if not API_KEY:
        logging.error("❌ API Key mancante!")
        return

    headers = {"x-apisports-key": API_KEY}
    base_url = "https://v3.football.api-sports.io"

    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    state = load_state()
    first_run = len(state) == 0
    alerts = []
    processed = 0

    for date in [today, tomorrow]:
        try:
            # Richiesta ODDS per Bet365 (ID 8)
            res = requests.get(f"{base_url}/odds", headers=headers, params={"date": date, "bookmaker": "8"}, timeout=15)
            
            if res.status_code == 429:
                logging.warning("⏳ Rate limit!")
                break
            if res.status_code != 200:
                logging.error(f" Errore API: {res.status_code}")
                continue

            data = res.json()
            matches = data.get("response", [])
            if not matches:
                logging.info(f"ℹ️ {date}: Nessuna partita")
                continue

            logging.info(f"✅ {date}: {len(matches)} partite trovate con quote Bet365")

            # 🔍 DEBUG: Analizziamo le prime 3 partite per conferma
            for i, m in enumerate(matches[:3]):
                try:
                    fixture = m.get("fixture", {})
                    teams = fixture.get("teams", {}) # CORREZIONE QUI
                    home = teams.get("home", {}).get("name", "Unknown")
                    away = teams.get("away", {}).get("name", "Unknown")
                    league = m.get("league", {}).get("name", "Unknown")
                    logging.info(f"   📊 Esempio {i+1}: {home} vs {away} ({league})")
                except Exception as e:
                    logging.error(f"   Errore debug: {e}")

            # Ora processiamo TUTTE le partite
            for m in matches:
                try:
                    fixture = m.get("fixture", {})
                    teams = fixture.get("teams", {})
                    home = teams.get("home", {}).get("name")
                    away = teams.get("away", {}).get("name")
                    fid = fixture.get("id")
                    league = m.get("league", {}).get("name")

                    if not all([home, away, fid, league]):
                        continue

                    bk = next((b for b in m.get("bookmakers", []) if b.get("id") == 8), None)
                    if not bk: continue

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
                                            alerts.append(f"📉 {v['value']}\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({drop:.1f}%↓)")

                                    state[key] = price
                                    processed += 1
                                except ValueError: continue
                except Exception as e:
                    logging.error(f" Errore processing {m.get('fixture',{}).get('id')}: {e}")

        except Exception as e:
            logging.error(f"❌ Errore critico {date}: {e}")

    save_state(state)
    if alerts:
        send_telegram("🚨 ALERT\n\n" + "\n\n".join(alerts[:10]))
        logging.info(f" Inviati {len(alerts)} alert")
    else:
        logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    run()
