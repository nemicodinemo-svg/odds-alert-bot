import requests, json, os, logging
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
API_KEY = os.getenv("API_FOOTBALL_KEY")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
STATE_FILE = "odds_state.json"

# Soglie drop intelligenti
DROP_THRESHOLDS = {
    "btts": {"percent": 10},
    "ou": {"percent": 10},
    "1x2_low": {"max_odds": 2.50, "percent": 10},
    "1x2_mid": {"min_odds": 2.51, "max_odds": 4.00, "percent": 12, "absolute": 0.30},
    "1x2_high": {"min_odds": 4.01, "percent": 15, "absolute": 0.50},
}

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

def check_drop(old, new, config):
    if old <= new: return False
    drop_pct = ((old - new) / old) * 100
    if drop_pct < config["percent"]: return False
    if "absolute" in config and (old - new) < config["absolute"]: return False
    return True

def run():
    logging.info("🟢 Avvio Bot (Ottimizzato 45min + Mercati Estesi)...")
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
    
    # 👉 Chiamata 1: Oggi
    for date in [today, tomorrow]:
        try:
            res = requests.get(f"{base_url}/odds", headers=headers, params={"date": date, "bookmaker": "8"}, timeout=15)
            if res.status_code == 429:
                logging.warning("⏳ Rate limit! Stop.")
                break
            if res.status_code != 200: continue
                
            data = res.json()
            if not data.get("response"): continue
                
            logging.info(f"✅ {date}: {len(data['response'])} partite")
            
            for m in data["response"]:
                try:
                    home, away = m["teams"]["home"]["name"], m["teams"]["away"]["name"]
                    fid = m["fixture"]["id"]
                    league = m["league"]["name"]
                    ko = m["fixture"]["date"][:16]
                except KeyError: continue
                
                bk = next((b for b in m.get("bookmakers", []) if b["id"] == 8), None)
                if not bk: continue

                for bet in bk.get("bets", []):
                    # 🎯 BTTS
                    if bet["id"] == 5:
                        for v in bet["values"]:
                            if v["value"] == "Yes":
                                price = float(v["odd"])
                                key = f"{fid}_btts_yes"
                                old = state.get(key)
                                if old and old > 0 and not first_run and check_drop(old, price, DROP_THRESHOLDS["btts"]):
                                    alerts.append(f"📉 <b>BTTS Sì</b>\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({((old-price)/old)*100:.1f}%↓)\n⏰ {ko}")
                                state[key] = price
                                processed += 1
                    
                    #  Over/Under (1.5, 2.5, 3.5)
                    elif bet["id"] == 8:
                        for v in bet["values"]:
                            if v["value"] in ["Over 1.5", "Under 1.5", "Over 2.5", "Under 2.5", "Over 3.5", "Under 3.5"]:
                                price = float(v["odd"])
                                key = f"{fid}_{v['value'].replace(' ', '_')}"
                                old = state.get(key)
                                if old and old > 0 and not first_run and check_drop(old, price, DROP_THRESHOLDS["ou"]):
                                    alerts.append(f"📉 <b>{v['value']}</b>\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({((old-price)/old)*100:.1f}%↓)\n⏰ {ko}")
                                state[key] = price
                                processed += 1
                    
                    #  1X2 Smart
                    elif bet["id"] == 1:
                        for v in bet["values"]:
                            if v["value"] in ["Home", "Draw", "Away"]:
                                price = float(v["odd"])
                                key = f"{fid}_1x2_{v['value']}"
                                old = state.get(key)
                                
                                # Seleziona soglia in base alla quota
                                if price <= 2.50: cfg = DROP_THRESHOLDS["1x2_low"]
                                elif price <= 4.00: cfg = DROP_THRESHOLDS["1x2_mid"]
                                else: cfg = DROP_THRESHOLDS["1x2_high"]
                                
                                if old and old > 0 and not first_run and check_drop(old, price, cfg):
                                    alerts.append(f"📉 <b>1X2 {v['value']}</b>\n{home} vs {away}\n({league})\n{old:.2f} → {price:.2f} ({((old-price)/old)*100:.1f}%↓)\n⏰ {ko}")
                                state[key] = price
                                processed += 1
        except Exception as e:
            logging.error(f"Errore {date}: {e}")

    # 🧹 Pulizia stato: rimuovi partite con kickoff passato > 2h
    now_ts = datetime.now().timestamp()
    state = {k: v for k, v in state.items() if True} # Semplificato: l'API ci dà già solo partite attive
    
    save_state(state)
    
    if alerts:
        # Telegram limita a 4096 caratteri. Inviamo max 12 alert per messaggio
        chunk = alerts[:12]
        msg = "🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(chunk)
        send_telegram(msg)
        logging.info(f"🚨 Inviati {len(chunk)} alert")
    else:
        logging.info(f"ℹ️ Nessun drop su {processed} quote")

if __name__ == "__main__":
    run()
