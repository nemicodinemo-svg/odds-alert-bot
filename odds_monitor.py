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
        with open(STATE_FILE, "r") as f: 
            return json.load(f)
    except: 
        return {}

def save_state(data):
    with open(STATE_FILE, "w") as f: 
        json.dump(data, f, indent=2)
    logging.info(f"💾 File salvato: {STATE_FILE} ({os.path.getsize(STATE_FILE)} bytes)")

def send_telegram(msg):
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        logging.info(f"Telegram: {r.status_code}")
    except Exception as e: 
        logging.error(f"Telegram Error: {e}")

def utc_to_italy(utc_str):
    try:
        utc_time = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        return (utc_time + timedelta(hours=2)).strftime("%d/%m %H:%M")
    except: 
        return utc_str[:16]

def extract_odds(match):
    odds = {}
    bookmakers = match.get("bookmakers", [])
    bet365 = next((b for b in bookmakers if b.get("id") == 8), None)
    if not bet365: return odds
    
    for bet in bet365.get("bets", []):
        bet_id = bet.get("id")
        values = {v["value"]: float(v["odd"]) for v in bet.get("values", []) if v.get("odd")}
        
        if bet_id == 1: odds["1x2"] = values
        elif bet_id == 5:
            if "Over 2.5" in values: odds["over_2.5"] = values["Over 2.5"]
            if "Under 2.5" in values: odds["under_2.5"] = values["Under 2.5"]
        elif bet_id == 8:
            if "Yes" in values: odds["btts_yes"] = values["Yes"]
            if "No" in values: odds["btts_no"] = values["No"]
    return odds

def run():
    logging.info(" Avvio Bot (Proxy Mode)...")
    if not PROXY_URL:
        logging.error(" PROXY_URL mancante!")
        save_state({}) # Fallback
        return

    try:
        logging.info(f"📡 Richiesta a: {PROXY_URL}")
        res = requests.get(PROXY_URL, timeout=15)
        
        if res.status_code != 200:
            logging.error(f"❌ Errore Proxy HTTP {res.status_code}")
            save_state({}) # Fallback
            return
        
        data = res.json()
        # Debug struttura risposta
        logging.info(f" Chiavi risposta proxy: {list(data.keys())}")
        
        football_data = data.get("football", {}).get("response", [])
        logging.info(f" Partite ricevute: {len(football_data)}")
        
        if not football_data:
            logging.warning("⚠️ Nessuna partita disponibile ora. Salvo stato vuoto.")
            save_state({}) # Fallback cruciale!
            return
            
        state = load_state()
        first_run = len(state) == 0
        if first_run: logging.info("🆘 Primo lancio: baseline creata")
        
        alerts = []
        processed = 0

        for match in football_data:
            try:
                fid = match.get("fixture", {}).get("id")
                if not fid: continue
                
                home = match.get("teams", {}).get("home", {}).get("name", "?")
                away = match.get("teams", {}).get("away", {}).get("name", "?")
                league = match.get("league", {}).get("name", "?")
                italy_time = utc_to_italy(match.get("fixture", {}).get("date", ""))
                
                odds = extract_odds(match)
                if not odds: continue
                
                for market, values in odds.items():
                    if isinstance(values, dict):
                        for outcome, price in values.items():
                            key = f"{fid}_{market}_{outcome}"
                            old = state.get(key)
                            if old and old > 0 and not first_run:
                                drop = ((old - price) / old) * 100
                                if drop >= 10:
                                    alerts.append(f"📉 <b>{outcome}</b> ({market})\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({drop:.1f}%↓)\n⏰ {italy_time}")
                            state[key] = price
                            processed += 1
                    else:
                        price = values
                        key = f"{fid}_{market}"
                        old = state.get(key)
                        if old and old > 0 and not first_run:
                            drop = ((old - price) / old) * 100
                            if drop >= 10:
                                alerts.append(f"📉 <b>{market}</b>\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({drop:.1f}%↓)\n⏰ {italy_time}")
                        state[key] = price
                        processed += 1
            except Exception as e:
                logging.error(f"⚠️ Errore match {fid}: {e}")

        save_state(state)
        
        if alerts:
            send_telegram(" <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts[:10]))
            logging.info(f"🚨 Inviati {len(alerts)} alert")
        else:
            logging.info(f"ℹ️ Nessun drop su {processed} quote")
        
        logging.info("🔄 Ciclo completato.")

    except Exception as e:
        logging.error(f"❌ Errore critico: {e}")
        save_state({}) # Fallback ultimo tentativo

if __name__ == "__main__":
    run()
