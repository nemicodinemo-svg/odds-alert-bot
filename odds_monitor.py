import requests, json, os, logging, sys
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
PROXY_URL = os.getenv("PROXY_URL")
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

def extract_odds(match):
    """Estrae le quote Bet365 da una partita (formato API-Football)"""
    odds = {}
    bookmakers = match.get("bookmakers", [])
    bet365 = next((b for b in bookmakers if b.get("id") == 8), None)
    
    if not bet365: return odds
    
    for bet in bet365.get("bets", []):
        bet_id = bet.get("id")
        values = {v["value"]: float(v["odd"]) for v in bet.get("values", []) if v.get("odd")}
        
        if bet_id == 1:  # 1X2
            odds["1x2"] = values
        elif bet_id == 5:  # Over/Under 2.5
            if "Over 2.5" in values: odds["over_2.5"] = values["Over 2.5"]
            if "Under 2.5" in values: odds["under_2.5"] = values["Under 2.5"]
        elif bet_id == 8:  # BTTS
            if "Yes" in values: odds["btts_yes"] = values["Yes"]
            if "No" in values: odds["btts_no"] = values["No"]
    
    return odds

def run():
    logging.info("🟢 Avvio Bot (Proxy Mode)...")
    if not PROXY_URL:
        logging.error("❌ PROXY_URL mancante!")
        return

    try:
        # 📥 Scarica dati dal Proxy
        logging.info(f"📡 Richiesta dati a: {PROXY_URL}")
        res = requests.get(PROXY_URL, timeout=15)
        
        if res.status_code != 200:
            logging.error(f"❌ Errore Proxy: {res.status_code} - {res.text}")
            return
        
        data = res.json()
        football_data = data.get("football", {}).get("response", [])
        
        if not football_data:
            logging.warning("⚠️ Nessuna partita ricevuta dal proxy")
            return
            
        logging.info(f"✅ Ricevute {len(football_data)} partite dal proxy")
        
        # 🔄 Elabora le partite
        state = load_state()
        first_run = len(state) == 0
        alerts = []
        processed = 0

        for match in football_data:
            try:
                fid = match.get("fixture", {}).get("id")
                if not fid: continue
                
                home = match.get("teams", {}).get("home", {}).get("name", "Unknown")
                away = match.get("teams", {}).get("away", {}).get("name", "Unknown")
                league = match.get("league", {}).get("name", "Unknown")
                fixture_date = match.get("fixture", {}).get("date", "")
                italy_time = utc_to_italy(fixture_date)
                
                # Estrai quote
                odds = extract_odds(match)
                if not odds: continue
                
                # Controlla ogni tipo di quota per drop
                for market, values in odds.items():
                    if isinstance(values, dict):  # Es: 1x2 con {"1": 2.10, "X": 3.40}
                        for outcome, price in values.items():
                            key = f"{fid}_{market}_{outcome}"
                            old = state.get(key)
                            
                            if old and old > 0 and not first_run:
                                drop = ((old - price) / old) * 100
                                if drop >= 10:
                                    alerts.append(
                                        f"📉 <b>{outcome}</b>\n"
                                        f"{home} vs {away}\n"
                                        f"({league})\n"
                                        f"{old:.2f} → {price:.2f} ({drop:.1f}%↓)\n"
                                        f"⏰ {italy_time}"
                                    )
                            
                            state[key] = price
                            processed += 1
                    else:  # Es: over_2.5 con valore singolo 1.85
                        price = values
                        key = f"{fid}_{market}"
                        old = state.get(key)
                        
                        if old and old > 0 and not first_run:
                            drop = ((old - price) / old) * 100
                            if drop >= 10:
                                alerts.append(
                                    f"📉 <b>{market}</b>\n"
                                    f"{home} vs {away}\n"
                                    f"({league})\n"
                                    f"{old:.2f} → {price:.2f} ({drop:.1f}%↓)\n"
                                    f"⏰ {italy_time}"
                                )
                        
                        state[key] = price
                        processed += 1
                        
            except Exception as e:
                logging.error(f"⚠️ Errore processing match {fid}: {e}")

        save_state(state)
        
        if alerts:
            send_telegram("🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
            logging.info(f"🚨 Inviati {len(alerts)} alert")
        else:
            logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
        
        logging.info("🔄 Ciclo completato.")

    except Exception as e:
        logging.error(f"❌ Errore critico: {e}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    run()
