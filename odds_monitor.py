import requests, json, os, logging
from datetime import datetime, timedelta

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
    logging.info("🟢 Avvio Bot (DEBUG COMPLETO)...")
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
            res = requests.get(f"{base_url}/odds", headers=headers, params={"date": date, "bookmaker": "8"}, timeout=15)
            
            if res.status_code != 200: continue

            data = res.json()
            matches = data.get("response", [])
            if not matches: continue

            logging.info(f"✅ {date}: {len(matches)} partite")

            # 🔍 STAMPIAMO LA STRUTTURA COMPLETA delle prime 2 partite
            for i, m in enumerate(matches[:2]):
                logging.info(f"\n{'='*60}")
                logging.info(f"PARTITA {i+1} - STRUTTURA COMPLETA:")
                logging.info(f"{'='*60}")
                logging.info(f"Chiavi principali: {list(m.keys())}")
                
                # Fixture
                fixture = m.get("fixture", {})
                logging.info(f"\nContenuto 'fixture': {json.dumps(fixture, indent=2)[:500]}")
                
                # League
                league = m.get("league", {})
                logging.info(f"\nContenuto 'league': {json.dumps(league, indent=2)[:300]}")
                
                # Bookmakers
                bks = m.get("bookmakers", [])
                if bks:
                    logging.info(f"\nBookmaker trovati: {len(bks)}")
                    logging.info(f"Primo bookmaker: {bks[0].get('name')} (ID: {bks[0].get('id')})")
                
                logging.info(f"{'='*60}\n")

            # Processamento normale
            for m in matches:
                try:
                    # Proviamo TUTTI i percorsi possibili per i nomi squadre
                    fixture = m.get("fixture", {})
                    
                    # Percorso 1: fixture.teams.home.name
                    teams = fixture.get("teams", {})
                    home = teams.get("home", {}).get("name") if teams else None
                    away = teams.get("away", {}).get("name") if teams else None
                    
                    # Percorso 2: fixture.home / fixture.away (diretto)
                    if not home: home = fixture.get("home", {}).get("name") or fixture.get("home")
                    if not away: away = fixture.get("away", {}).get("name") or fixture.get("away")
                    
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
                    logging.error(f" Errore: {e}")

        except Exception as e:
            logging.error(f"❌ Errore critico {date}: {e}")

    save_state(state)
    if alerts:
        send_telegram("🚨 ALERT\n\n" + "\n\n".join(alerts[:10]))
    else:
        logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    run()
