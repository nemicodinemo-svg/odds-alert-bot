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
    """Carica stato precedente"""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.warning(f"⚠️ Nessun stato precedente: {e}")
        return {"matches": {}}

def save_state(state):
    """Salva stato aggiornato"""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
    logging.info(f"💾 Stato salvato: {STATE_FILE} ({os.path.getsize(STATE_FILE)} bytes)")

def send_telegram(msg):
    """Invia alert a Telegram"""
    if not TG_TOKEN or not TG_CHAT_ID: return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
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

def is_match_started(fixture_date):
    """Controlla se la partita è già iniziata"""
    try:
        kickoff = datetime.fromisoformat(fixture_date.replace('Z', '+00:00'))
        now = datetime.now(kickoff.tzinfo)
        # ✅ MODIFICA: Considera iniziata SOLO se sono passati 5 minuti dal fischio d'inizio
        # Prima era -90 minuti (ignorava le partite imminenti). Ora è +5 minuti.
        return (now - kickoff).total_seconds() > 300 
    except:
        return False

def extract_odds(match):
    """Estrae quote Bet365 (ID=8)"""
    odds = {}
    bookmakers = match.get("bookmakers", [])
    bet365 = next((b for b in bookmakers if b.get("id") == 8), None)
    if not bet365: return odds
    
    for bet in bet365.get("bets", []):
        bet_id = bet.get("id")
        values = {}
        for v in bet.get("values", []):
            if v.get("odd"):
                try: values[v["value"]] = float(v["odd"])
                except: pass
        
        if bet_id == 1: odds["1x2"] = values
        elif bet_id == 5:
            if "Over 2.5" in values: odds["over_2.5"] = values["Over 2.5"]
            if "Under 2.5" in values: odds["under_2.5"] = values["Under 2.5"]
        elif bet_id == 8:
            if "Yes" in values: odds["btts_yes"] = values["Yes"]
            if "No" in values: odds["btts_no"] = values["No"]
    return odds

def run():
    logging.info("🟢 Avvio Bot (Match-Based Monitoring)...")
    
    if not PROXY_URL:
        logging.error("❌ PROXY_URL mancante!")
        return

    try:
        # 1. Scarica dati dal Proxy
        res = requests.get(PROXY_URL, timeout=15)
        if res.status_code != 200:
            logging.error(f"❌ Errore Proxy HTTP {res.status_code}")
            return
        
        data = res.json()
        football_data = data.get("football", {}).get("response", [])
        
        if not football_data:
            logging.warning("⚠️ Nessuna partita ricevuta")
            return
        
        logging.info(f"✅ Ricevute {len(football_data)} partite")
        
        # 2. Carica stato (match monitorati)
        state = load_state()
        matches = state.get("matches", {})
        
        alerts = []
        new_matches = 0
        active_matches = 0
        finished_matches = 0
        
        # 3. Processa partite attuali
        current_match_ids = set()
        
        for match in football_data:
            try:
                fid = match.get("fixture", {}).get("id")
                if not fid: continue
                
                current_match_ids.add(fid)
                
                home = match.get("teams", {}).get("home", {}).get("name", "Unknown")
                away = match.get("teams", {}).get("away", {}).get("name", "Unknown")
                league = match.get("league", {}).get("name", "Unknown League")
                fixture_date = match.get("fixture", {}).get("date", "")
                italy_time = utc_to_italy(fixture_date)
                
                # DEBUG: Stampa orario per capire cosa succede
                logging.debug(f" Controllo: {home} vs {away} @ {italy_time}")

                # Verifica se partita già iniziata
                if is_match_started(fixture_date):
                    if fid in matches:
                        finished_matches += 1
                        # Non rimuovere subito, ma segnala
                        # logging.debug(f"⏭️ Partita iniziata: {home} vs {away}")
                    continue  # Salta partite già iniziate
                
                active_matches += 1
                
                # Estrai quote attuali
                current_odds = extract_odds(match)
                if not current_odds: continue
                
                # 4. Gestione match
                if fid not in matches:
                    # NUOVA PARTITA → Crea baseline
                    matches[fid] = {
                        "home": home,
                        "away": away,
                        "league": league,
                        "kickoff": fixture_date,
                        "first_seen": datetime.now().isoformat(),
                        "baseline_odds": current_odds,
                        "last_check": datetime.now().isoformat()
                    }
                    new_matches += 1
                    logging.info(f"➕ Nuova partita monitorata: {home} vs {away} ({italy_time})")
                else:
                    # PARTITA GIÀ MONITORATA → Confronta con baseline
                    match_info = matches[fid]
                    baseline_odds = match_info.get("baseline_odds", {})
                    
                    # Confronta ogni quota
                    for market, baseline_values in baseline_odds.items():
                        if market not in current_odds: continue
                        
                        current_values = current_odds[market]
                        
                        if isinstance(baseline_values, dict):
                            for outcome, base_price in baseline_values.items():
                                if outcome not in current_values: continue
                                
                                current_price = current_values[outcome]
                                drop_pct = ((current_price - base_price) / base_price) * 100
                                
                                # 📉 ALERT DROP >= 10%
                                if drop_pct <= -10:
                                    alerts.append(
                                        f"📉 <b>{outcome}</b> ({market})\n"
                                        f"<b>{home} vs {away}</b>\n"
                                        f"({league})\n"
                                        f" Baseline: {base_price:.2f}\n"
                                        f"📊 Attuale: {current_price:.2f}\n"
                                        f"🔻 Drop: {abs(drop_pct):.1f}%\n"
                                        f"⏰ {italy_time}"
                                    )
                                    logging.info(f"🎯 DROP: {home} vs {away} - {outcome} {base_price:.2f}→{current_price:.2f}")
                        
                        else:
                            # Quote singole
                            base_price = baseline_values
                            current_price = current_values
                            drop_pct = ((current_price - base_price) / base_price) * 100
                            
                            if drop_pct <= -10:
                                alerts.append(
                                    f"📉 <b>{market}</b>\n"
                                    f"<b>{home} vs {away}</b>\n"
                                    f"({league})\n"
                                    f" Baseline: {base_price:.2f}\n"
                                    f"📊 Attuale: {current_price:.2f}\n"
                                    f"🔻 Drop: {abs(drop_pct):.1f}%\n"
                                    f"⏰ {italy_time}"
                                )
                    
                    # Aggiorna timestamp ultimo controllo
                    match_info["last_check"] = datetime.now().isoformat()
                
            except Exception as e:
                logging.error(f"️ Errore match {fid}: {e}")
        
        # 5. Rimuovi partite vecchie o giocate
        old_count = len(matches)
        matches = {fid: m for fid, m in matches.items() if fid in current_match_ids}
        removed = old_count - len(matches)
        if removed > 0:
            logging.info(f"🧹 Rimosse {removed} partite (giocate o non più in palinsesto)")
        
        # 6. Salva stato
        state["matches"] = matches
        save_state(state)
        
        # 7. Invia alert
        if alerts:
            msg = "🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts[:10])
            send_telegram(msg)
            logging.info(f"🚨 Inviati {len(alerts)} alert")
        else:
            logging.info(f"ℹ️ Nessun drop. Monitoraggio attivo su {active_matches} partite ({new_matches} nuove)")
        
        logging.info(f"🔄 Ciclo completato.")

    except Exception as e:
        logging.error(f"❌ Errore critico: {e}")
        import traceback
        logging.error(traceback.format_exc())

if __name__ == "__main__":
    run()
