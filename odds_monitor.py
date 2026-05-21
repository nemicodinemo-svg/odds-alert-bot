#!/usr/bin/env python3
import os
import json
import logging
import requests
from datetime import datetime, timedelta
import pytz

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('odds_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Variabili d'ambiente
PROXY_URL = os.getenv('PROXY_URL')
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN')
TG_CHAT_ID = os.getenv('TG_CHAT_ID')

def load_state():
    """Carica lo stato dal file JSON"""
    try:
        if os.path.exists('odds_state.json'):
            with open('odds_state.json', 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"❌ Errore caricamento stato: {e}")
    return {"matches": {}}

def save_state(state):
    """Salva lo stato nel file JSON"""
    try:
        with open('odds_state.json', 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
        logging.info("💾 Stato salvato: odds_state.json")
    except Exception as e:
        logging.error(f"❌ Errore salvataggio stato: {e}")

def send_telegram(message):
    """Invia messaggio Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TG_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        res = requests.post(url, json=data, timeout=10)
        if res.status_code == 200:
            logging.info("✅ Alert Telegram inviato")
        else:
            logging.error(f"❌ Errore Telegram: {res.text}")
    except Exception as e:
        logging.error(f"❌ Errore invio Telegram: {e}")

def utc_to_italy(utc_date_str):
    """Converte data UTC in Italia"""
    try:
        if not utc_date_str:
            return "N/A"
        utc_dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        italy_tz = pytz.timezone('Europe/Rome')
        italy_dt = utc_dt.astimezone(italy_tz)
        return italy_dt.strftime('%d/%m %H:%M')
    except:
        return utc_date_str

def is_match_started(fixture_date):
    """Verifica se la partita è già iniziata"""
    try:
        if not fixture_date:
            return True
        match_time = datetime.fromisoformat(fixture_date.replace('Z', '+00:00'))
        now = datetime.now(pytz.UTC)
        return match_time <= now
    except:
        return True

def extract_odds(match_data):
    """Estrae quote Bet365 dalla partita"""
    odds = {}
    bookmakers = match_data.get("bookmakers", [])
    
    for bookmaker in bookmakers:
        if bookmaker.get("name") == "Bet365" or bookmaker.get("id") == 8:
            for bet in bookmaker.get("bets", []):
                bet_name = bet.get("name", "")
                values = bet.get("values", [])
                
                if "Match Winner" in bet_name or "1X2" in bet_name:
                    for v in values:
                        val = v.get("value", "")
                        odd = v.get("odd", "")
                        if val and odd:
                            try:
                                odds[f"1X2_{val}"] = float(odd)
                            except:
                                pass
                
                elif "Goals Over/Under" in bet_name or "Over/Under" in bet_name:
                    for v in values:
                        val = v.get("value", "")
                        odd = v.get("odd", "")
                        if val and odd:
                            try:
                                odds[f"O/U_{val.replace(' ', '')}"] = float(odd)
                            except:
                                pass
                
                elif "Both Teams Score" in bet_name or "BTTS" in bet_name:
                    for v in values:
                        val = v.get("value", "")
                        odd = v.get("odd", "")
                        if val and odd:
                            try:
                                odds[f"BTTS_{val}"] = float(odd)
                            except:
                                pass
    
    return odds

def run():
    logging.info("🟢 Avvio Bot (Match-Based Monitoring)...")
    
    if not PROXY_URL:
        logging.error("❌ PROXY_URL mancante!")
        save_state({"matches": {}})
        return
    
    try:
        # 1. Scarica dati dal Proxy
        logging.info(f"📡 Richiesta a: {PROXY_URL}")
        res = requests.get(PROXY_URL, timeout=15)
        
        if res.status_code != 200:
            logging.error(f"❌ Errore Proxy HTTP {res.status_code}")
            save_state({"matches": {}})
            return
        
        data = res.json()
        
        # 🔍 DEBUG: Mostra data e struttura
        debug = data.get("debug", {})
        logging.info(f"🔍 DEBUG Proxy - Data Italia: {debug.get('italy_date', 'N/A')}")
        logging.info(f"🔍 DEBUG Proxy - Partite ricevute: {debug.get('total_matches', 0)}")
        
        football_data = data.get("football", {}).get("response", [])
        
        if not football_data:
            logging.warning("⚠️ Nessuna partita ricevuta (normale in orari notturni)")
            logging.info(f"📊 Debug completo: {json.dumps(debug, indent=2)}")
            save_state({"matches": {}})
            return
        
        logging.info(f"✅ Ricevute {len(football_data)} partite")
        
        # 🔍 DEBUG: Mostra struttura PRIMA partita
        if football_data:
            first_match = football_data[0]
            logging.info("🔍 DEBUG - Struttura prima partita:")
            teams = first_match.get("teams", {})
            logging.info(f"   Teams dict: {json.dumps(teams, indent=2)[:500]}")
            logging.info(f"   Home: {teams.get('home', {}).get('name', 'Unknown')}")
            logging.info(f"   Away: {teams.get('away', {}).get('name', 'Unknown')}")
        
        # 2. Carica stato (match monitorati)
        state = load_state()
        matches = state.get("matches", {})
        alerts = []
        new_matches = 0
        active_matches = 0
        
        # 3. Processa partite attuali
        current_match_ids = set()
        
        for match in football_data:
            try:
                fid = match.get("fixture", {}).get("id")
                if not fid:
                    continue
                
                current_match_ids.add(fid)
                
                # Estrai info partita con fallback robusti
                teams = match.get("teams", {})
                home_team = teams.get("home", {})
                away_team = teams.get("away", {})
                
                # Nomi squadre - gerarchia robusta
                home = (
                    home_team.get("name") or 
                    home_team.get("team", {}).get("name") if isinstance(home_team.get("team"), dict) else None or
                    home_team.get("winner") or 
                    home_team.get("short_name") or
                    home_team.get("code") or
                    str(home_team) if isinstance(home_team, str) else "Unknown Home"
                )
                
                away = (
                    away_team.get("name") or 
                    away_team.get("team", {}).get("name") if isinstance(away_team.get("team"), dict) else None or
                    away_team.get("winner") or 
                    away_team.get("short_name") or
                    away_team.get("code") or
                    str(away_team) if isinstance(away_team, str) else "Unknown Away"
                )
                
                league = match.get("league", {}).get("name", "Unknown League")
                fixture_date = match.get("fixture", {}).get("date", "")
                italy_time = utc_to_italy(fixture_date)
                
                logging.info(f"   Match: {home} vs {away} @ {italy_time}")
                
                # Verifica se partita già iniziata
                if is_match_started(fixture_date):
                    if fid in matches:
                        logging.info(f"   ⏭️ Partita iniziata, rimossa: {home} vs {away}")
                    continue
                
                active_matches += 1
                
                # Estrai quote
                current_odds = extract_odds(match)
                
                if not current_odds:
                    logging.info(f"   ⚠️ Nessuna quota Bet365 trovata per {home} vs {away}")
                    continue
                
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
                    logging.info(f"   ➕ Nuova partita monitorata: {home} vs {away}")
                else:
                    # PARTITA GIÀ MONITORATA → Confronta con baseline
                    match_info = matches[fid]
                    baseline_odds = match_info.get("baseline_odds", {})
                    
                    # Confronta ogni quota
                    for market, baseline_price in baseline_odds.items():
                        if market not in current_odds:
                            continue
                        
                        current_price = current_odds[market]
                        
                        try:
                            drop_pct = ((current_price - baseline_price) / baseline_price) * 100
                            
                            # 📉 ALERT DROP >= 10%
                            if drop_pct <= -10:
                                alerts.append(
                                    f"📉 <b>{market}</b>\n"
                                    f"<b>{home} vs {away}</b>\n"
                                    f"({league})\n"
                                    f"📊 Baseline: {baseline_price:.2f}\n"
                                    f"📊 Attuale: {current_price:.2f}\n"
                                    f"🔻 Drop: {abs(drop_pct):.1f}%\n"
                                    f"⏰ {italy_time}"
                                )
                                logging.info(f"   🎯 DROP: {home} vs {away} - {market} {baseline_price:.2f}→{current_price:.2f} ({drop_pct:.1f}%)")
                        except Exception as e:
                            logging.error(f"   ⚠️ Errore confronto quote: {e}")
                    
                    # Aggiorna timestamp ultimo controllo
                    match_info["last_check"] = datetime.now().isoformat()
            
            except Exception as e:
                logging.error(f"⚠️ Errore match {fid}: {e}")
                import traceback
                logging.error(traceback.format_exc())
        
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
            # Rimuovi duplicati (stessa partita, tieni solo il drop maggiore)
            unique_alerts = []
            seen_matches = {}
            
            for alert in alerts:
                lines = alert.split("\n")
                if len(lines) > 1:
                    match_key = lines[1]  # "Home vs Away"
                    drop_line = [l for l in lines if "🔻 Drop:" in l]
                    if drop_line:
                        drop_pct = float(drop_line[0].split(":")[1].strip().replace("%", ""))
                    else:
                        drop_pct = 0
                    
                    if match_key not in seen_matches or drop_pct > seen_matches[match_key]:
                        seen_matches[match_key] = drop_pct
                        unique_alerts.append(alert)
            
            msg = "🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(unique_alerts[:10])
            send_telegram(msg)
            logging.info(f"🚨 Inviati {len(unique_alerts)} alert unici")
        else:
            logging.info(f"ℹ️ Nessun drop. Monitoraggio attivo su {active_matches} partite ({new_matches} nuove)")
        
        logging.info(f"🔄 Ciclo completato.")
    
    except Exception as e:
        logging.error(f"❌ Errore critico: {e}")
        import traceback
        logging.error(traceback.format_exc())
        save_state({"matches": {}})

if __name__ == "__main__":
    run()
