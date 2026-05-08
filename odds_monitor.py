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
    logging.info("🟢 Avvio Bot (DEBUG MODE)...")
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
                logging.error(f"❌ Errore API: {res.status_code} - {res.text}")
                continue
                
            data = res.json()
            if not data.get("response"):
                logging.info(f"ℹ️ {date}: Nessuna risposta dall'API")
                continue
            
            logging.info(f"✅ {date}: {len(data['response'])} partite trovate")
            
            # 🔍 DEBUG: Analizziamo ogni partita
            for i, m in enumerate(data["response"][:3]):  # Analizziamo solo le prime 3 per non spammare
                try:
                    home = m["teams"]["home"]["name"]
                    away = m["teams"]["away"]["name"]
                    league = m["league"]["name"]
                    fid = m["fixture"]["id"]
                    
                    logging.info(f"\n📊 PARTITA {i+1}: {home} vs {away}")
                    logging.info(f"   Campionato: {league}")
                    logging.info(f"   Fixture ID: {fid}")
                    
                    # Controlliamo TUTTI i bookmaker disponibili
                    bookmakers = m.get("bookmakers", [])
                    logging.info(f"   Bookmaker disponibili: {len(bookmakers)}")
                    
                    bk_names = [bk.get("name", "Unknown") for bk in bookmakers]
                    logging.info(f"   Lista: {', '.join(bk_names[:10])}")  # Primi 10
                    
                    # Cerchiamo Bet365 specificamente
                    bk_365 = next((bk for bk in bookmakers if bk["id"] == 8), None)
                    
                    if bk_365:
                        logging.info(f"   ✅ Bet365 TROVATO!")
                        bets = bk_365.get("bets", [])
                        logging.info(f"   Mercati disponibili: {len(bets)}")
                        for bet in bets:
                            logging.info(f"     - {bet.get('name', 'Unknown')} (ID: {bet.get('id')})")
                    else:
                        logging.info(f"   ❌ Bet365 NON TROVATO per questa partita!")
                    
                except Exception as e:
                    logging.error(f"   Errore analisi partita: {e}")
            
            # Ora processiamo normalmente tutte le partite
            for m in data["response"]:
                try:
                    home = m["teams"]["home"]["name"]
                    away = m["teams"]["away"]["name"]
                    fid = m["fixture"]["id"]
                    league = m["league"]["name"]
                    
                    bk = next((b for b in m.get("bookmakers", []) if b["id"] == 8), None)
                    if not bk:
                        continue
                    
                    for bet in bk.get("bets", []):
                        if bet["id"] in [1, 5, 8]:  # 1X2, BTTS, Over/Under
                            for v in bet["values"]:
                                price = float(v["odd"])
                                key = f"{fid}_{bet['id']}_{v['value'].replace(' ', '_')}"
                                old = state.get(key)
                                
                                if old and old > 0 and not first_run:
                                    drop = ((old - price) / old) * 100
                                    if drop >= 10:
                                        alerts.append(f"📉 {v['value']}\n{home} vs {away}\n{old:.2f} → {price:.2f} ({drop:.1f}%↓)")
                                
                                state[key] = price
                                processed += 1
                                
                except Exception as e:
                    logging.error(f"Errore processing: {e}")
                    
        except Exception as e:
            logging.error(f"Errore critico {date}: {e}")

    save_state(state)
    
    if alerts:
        msg = "🚨 ALERT\n\n" + "\n\n".join(alerts[:10])
        send_telegram(msg)
        logging.info(f"🚨 Inviati {len(alerts)} alert")
    else:
        logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
    
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    run()
