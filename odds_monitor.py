import requests, json, os, logging, sys
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
PROXY_URL = os.getenv("PROXY_URL")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
STATE_FILE = "odds_state.json"

# ⏰ FINESTRA TEMPORALE (ore)
BASELINE_HOURS = 24  # Confronta con baseline delle ultime 24 ore
CLEANUP_HOURS = 48   # Rimuovi partite vecchie di 48 ore

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
    """Carica stato precedente con timestamp"""
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        
        # Controlla età della baseline
        updated_at = state.get("updated_at")
        if updated_at:
            baseline_time = datetime.fromisoformat(updated_at)
            hours_old = (datetime.now() - baseline_time).total_seconds() / 3600
            
            if hours_old > BASELINE_HOURS:
                logging.info(f"⏰ Baseline vecchia di {hours_old:.1f}h → RESET (soglia: {BASELINE_HOURS}h)")
                return {"odds": {}, "matches": {}, "updated_at": None}
        
        return state
    except Exception as e:
        logging.warning(f"⚠️ Nessun stato precedente: {e}")
        return {"odds": {}, "matches": {}, "updated_at": None}

def save_state(state):
    """Salva stato con timestamp"""
    state["updated_at"] = datetime.now().isoformat()
    
    # Pulisci partite vecchie
    if "matches" in state:
        cutoff = datetime.now() - timedelta(hours=CLEANUP_HOURS)
        old_count = len(state["matches"])
        state["matches"] = {
            fid: m for fid, m in state["matches"].items()
            if datetime.fromisoformat(m.get("first_seen", datetime.now().isoformat())) > cutoff
        }
        removed = old_count - len(state["matches"])
        if removed > 0:
            logging.info(f"🧹 Rimosse {removed} partite vecchie")
    
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    
    logging.info(f"💾 Stato salvato: {STATE_FILE} ({os.path.getsize(STATE_FILE)} bytes)")

def send_telegram(msg):
    """Invia alert a Telegram"""
    if not TG_TOKEN or not TG_CHAT_ID:
        logging.warning("⚠️ Telegram non configurato")
        return
    
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TG_CHAT_ID,
            "text": msg,
            "parse_mode": "HTML"
        }, timeout=10)
        logging.info(f"✅ Telegram: {r.status_code}")
    except Exception as e:
        logging.error(f"❌ Telegram Error: {e}")

def utc_to_italy(utc_str):
    """Converte UTC in ora italiana"""
    try:
        utc_time = datetime.fromisoformat(utc_str.replace('Z', '+00:00'))
        return (utc_time + timedelta(hours=2)).strftime("%d/%m %H:%M")
    except:
        return utc_str[:16] if utc_str else "??"

def extract_odds(match):
    """Estrae quote Bet365 (ID=8) dalla partita"""
    odds = {}
    bookmakers = match.get("bookmakers", [])
    
    # Cerca Bet365
    bet365 = next((b for b in bookmakers if b.get("id") == 8), None)
    if not bet365:
        return odds
    
    for bet in bet365.get("bets", []):
        bet_id = bet.get("id")
        values = {}
        for v in bet.get("values", []):
            if v.get("odd"):
                try:
                    values[v["value"]] = float(v["odd"])
                except:
                    pass
        
        if bet_id == 1:  # 1X2
            odds["1x2"] = values
        elif bet_id == 5:  # Over/Under 2.5
            if "Over 2.5" in values:
                odds["over_2.5"] = values["Over 2.5"]
            if "Under 2.5" in values:
                odds["under_2.5"] = values["Under 2.5"]
        elif bet_id == 8:  # BTTS
            if "Yes" in values:
                odds["btts_yes"] = values["Yes"]
            if "No" in values:
                odds["btts_no"] = values["No"]
    
    return odds

def run():
    logging.info("🟢 Avvio Bot (Proxy Mode)...")
    
    if not PROXY_URL:
        logging.error("❌ PROXY_URL mancante!")
        save_state({"odds": {}, "matches": {}, "updated_at": None})
        return

    try:
        # 1. Scarica dati dal Proxy
        logging.info(f"📡 Richiesta a: {PROXY_URL}")
        res = requests.get(PROXY_URL, timeout=15)
        
        if res.status_code != 200:
            logging.error(f"❌ Errore Proxy HTTP {res.status_code}")
            save_state({"odds": {}, "matches": {}, "updated_at": None})
            return
        
        data = res.json()
        football_data = data.get("football", {}).get("response", [])
        
        if not football_data:
            logging.warning("⚠️ Nessuna partita ricevuta (normale in orari notturni)")
            save_state({"odds": {}, "matches": {}, "updated_at": None})
            return
        
        logging.info(f"✅ Ricevute {len(football_data)} partite")
        
        # 2. Carica stato precedente
        state = load_state()
        old_odds = state.get("odds", {})
        old_matches = state.get("matches", {})
        first_run = len(old_odds) == 0
        
        if first_run:
            logging.info("🆘 Primo lancio o baseline resettata → creo baseline")
        
        # 3. Analizza partite
        alerts = []
        processed = 0
        new_matches = 0
        drops_found = 0
        
        for match in football_data:
            try:
                fid = match.get("fixture", {}).get("id")
                if not fid:
                    continue
                
                # Estrai info partita (con fallback)
                home = match.get("teams", {}).get("home", {}).get("name")
                away = match.get("teams", {}).get("away", {}).get("name")
                league = match.get("league", {}).get("name", "Unknown League")
                fixture_date = match.get("fixture", {}).get("date", "")
                italy_time = utc_to_italy(fixture_date)
                
                # Fallback per nomi squadre
                if not home:
                    home = match.get("teams", {}).get("home", {}).get("winner", "Unknown Home")
                if not away:
                    away = match.get("teams", {}).get("away", {}).get("winner", "Unknown Away")
                
                # Salva info partita se nuova
                if fid not in old_matches:
                    old_matches[fid] = {
                        "home": home,
                        "away": away,
                        "league": league,
                        "date": fixture_date,
                        "first_seen": datetime.now().isoformat()
                    }
                    new_matches += 1
                    logging.debug(f"➕ Nuova partita: {home} vs {away}")
                
                # Estrai quote
                odds = extract_odds(match)
                if not odds:
                    continue
                
                # Confronta quote con baseline
                for market, values in odds.items():
                    if isinstance(values, dict):
                        for outcome, price in values.items():
                            key = f"{fid}_{market}_{outcome}"
                            baseline = old_odds.get(key)
                            
                            # Se esiste baseline e non è primo run
                            if baseline and baseline > 0 and not first_run:
                                change = ((price - baseline) / baseline) * 100
                                
                                # ✅ SOLO DROP >= 10% (rimossi aumenti)
                                if change <= -10:
                                    drops_found += 1
                                    alerts.append(
                                        f"📉 <b>{outcome}</b> ({market})\n"
                                        f"<b>{home} vs {away}</b>\n"
                                        f"({league})\n"
                                        f"📊 Quota iniziale: {baseline:.2f}\n"
                                        f"📊 Quota attuale: {price:.2f}\n"
                                        f"🔻 Drop: {abs(change):.1f}%\n"
                                        f"⏰ {italy_time}"
                                    )
                                    logging.info(f"🎯 DROP trovato: {home} vs {away} - {outcome} {baseline:.2f}→{price:.2f}")
                            
                            # Salva quota attuale
                            old_odds[key] = price
                            processed += 1
                            
                    else:
                        # Quote singole (es: over_2.5)
                        price = values
                        key = f"{fid}_{market}"
                        baseline = old_odds.get(key)
                        
                        if baseline and baseline > 0 and not first_run:
                            change = ((price - baseline) / baseline) * 100
                            
                            # ✅ SOLO DROP >= 10%
                            if change <= -10:
                                drops_found += 1
                                alerts.append(
                                    f"📉 <b>{market}</b>\n"
                                    f"<b>{home} vs {away}</b>\n"
                                    f"({league})\n"
                                    f"📊 Quota iniziale: {baseline:.2f}\n"
                                    f"📊 Quota attuale: {price:.2f}\n"
                                    f"🔻 Drop: {abs(change):.1f}%\n"
                                    f"⏰ {italy_time}"
                                )
                                logging.info(f"🎯 DROP trovato: {home} vs {away} - {market} {baseline:.2f}→{price:.2f}")
                        
                        old_odds[key] = price
                        processed += 1
                        
            except Exception as e:
                logging.error(f"⚠️ Errore match {fid}: {e}")
        
        # 4. Salva stato aggiornato
        state = {
            "odds": old_odds,
            "matches": old_matches,
            "updated_at": datetime.now().isoformat()
        }
        save_state(state)
        
        # 5. Invia alert
        if alerts:
            # Rimuovi duplicati (stessa partita, mercati diversi - tieni solo il drop maggiore)
            unique_alerts = []
            seen_matches = {}
            for alert in alerts:
                lines = alert.split("\n")
                if len(lines) > 1:
                    match_key = lines[1]  # "Home vs Away"
                    # Estrai percentuale drop
                    drop_line = [l for l in lines if "🔻 Drop:" in l][0] if any("🔻 Drop:" in l for l in lines) else ""
                    drop_pct = float(drop_line.split(":")[1].strip().replace("%", "")) if drop_line else 0
                    
                    if match_key not in seen_matches or drop_pct > seen_matches[match_key]:
                        seen_matches[match_key] = drop_pct
                        unique_alerts.append(alert)
            
            msg = "🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(unique_alerts[:10])
            send_telegram(msg)
            logging.info(f"🚨 Inviati {len(unique_alerts)} alert unici ({drops_found} drop totali)")
        else:
            logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate ({new_matches} nuove partite)")
        
        logging.info(f"🔄 Ciclo completato. Baseline: {len(old_odds)} quote, {len(old_matches)} partite")

    except Exception as e:
        logging.error(f"❌ Errore critico: {e}")
        import traceback
        logging.error(traceback.format_exc())
        save_state({"odds": {}, "matches": {}, "updated_at": None})

if __name__ == "__main__":
    run()
