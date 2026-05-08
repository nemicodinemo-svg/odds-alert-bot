import requests, json, os, logging
from datetime import datetime, timedelta

# 🔑 CONFIGURAZIONE
API_KEY = os.getenv("API_FOOTBALL_KEY")
TG_TOKEN = os.getenv("TG_BOT_TOKEN")
TG_CHAT_ID = os.getenv("TG_CHAT_ID")
STATE_FILE = "odds_state.json"

# Configurazione logging
logging.basicConfig(
    filename="odds_monitor.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    filemode="a"
)

def load_state():
    """Carica lo stato precedente dal file JSON"""
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logging.info("📄 Nessun file di stato trovato, parto da zero")
        return {}
    except json.JSONDecodeError:
        logging.warning("⚠️ File di stato corrotto, resetto")
        return {}

def save_state(data):
    """Salva lo stato attuale nel file JSON"""
    with open(STATE_FILE, "w") as f:
        json.dump(data, f, indent=2)

def send_telegram(msg):
    """Invia messaggio a Telegram con gestione errori"""
    if not TG_TOKEN or not TG_CHAT_ID:
        logging.warning("⚠️ Credenziali Telegram mancanti")
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": TG_CHAT_ID, "text": msg, "parse_mode": "HTML"},
            timeout=10
        )
        if r.status_code == 200:
            logging.info("✅ Alert inviato su Telegram")
        else:
            logging.error(f"❌ Telegram error {r.status_code}: {r.text}")
    except Exception as e:
        logging.error(f"❌ Telegram Exception: {e}")

def utc_to_italy(utc_str):
    """Converte stringa data UTC in formato leggibile italiano (DD/MM HH:MM)"""
    try:
        # Pulizia stringa e parsing
        clean_str = utc_str.replace('Z', '+00:00')
        utc_time = datetime.fromisoformat(clean_str)
        # Conversione UTC → Italia (UTC+2 per ora legale estiva)
        italy_time = utc_time + timedelta(hours=2)
        return italy_time.strftime("%d/%m %H:%M")
    except:
        # Fallback in caso di errore di parsing
        return utc_str[:16]

def fetch_teams_cache(dates, headers, base_url):
    """Scarica i nomi delle squadre per le date richieste"""
    cache = {}
    for date in dates:
        try:
            res = requests.get(
                f"{base_url}/fixtures",
                headers=headers,
                params={"date": date},
                timeout=10
            )
            if res.status_code == 200:
                for fix in res.json().get("response", []):
                    fid = fix["fixture"]["id"]
                    teams = fix.get("teams", {})
                    league = fix.get("league", {})
                    if teams.get("home") and teams.get("away"):
                        cache[fid] = {
                            "home": teams["home"]["name"],
                            "away": teams["away"]["name"],
                            "league": league.get("name", "Unknown")
                        }
        except Exception as e:
            logging.warning(f"⚠️ Errore cache squadre {date}: {e}")
    return cache

def run():
    logging.info("🟢 Avvio Bot (Versione Ottimizzata IT)...")
    
    if not API_KEY:
        logging.error("❌ API Key mancante!")
        return

    headers = {"x-apisports-key": API_KEY}
    base_url = "https://v3.football.api-sports.io"

    today = datetime.now().strftime("%Y-%m-%d")
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    dates = [today, tomorrow]

    # 1️⃣ Scarica cache nomi squadre
    teams_cache = fetch_teams_cache(dates, headers, base_url)
    logging.info(f"📦 Cache squadre: {len(teams_cache)} partite")

    state = load_state()
    first_run = len(state) == 0
    alerts = []
    processed = 0

    # 2️⃣ Scarica quote Bet365
    for date in dates:
        try:
            res = requests.get(
                f"{base_url}/odds",
                headers=headers,
                params={"date": date, "bookmaker": "8"},
                timeout=15
            )
            
            if res.status_code == 429:
                logging.warning("⏳ Rate limit API raggiunto!")
                break
            if res.status_code != 200:
                logging.warning(f"⚠️ API error {res.status_code} per {date}")
                continue

            data = res.json()
            matches = data.get("response", [])
            if not matches:
                logging.info(f"ℹ️ {date}: Nessuna partita con quote Bet365")
                continue

            logging.info(f"✅ {date}: {len(matches)} partite con quote Bet365")

            for m in matches:
                try:
                    fid = m.get("fixture", {}).get("id")
                    if not fid or fid not in teams_cache:
                        continue
                    
                    # Recupera dati dalla cache
                    home = teams_cache[fid]["home"]
                    away = teams_cache[fid]["away"]
                    league = teams_cache[fid]["league"]
                    fixture_date = m.get("fixture", {}).get("date", "")
                    italy_time = utc_to_italy(fixture_date)

                    # Cerca Bet365 (ID 8)
                    bk = next((b for b in m.get("bookmakers", []) if b.get("id") == 8), None)
                    if not bk:
                        continue

                    for bet in bk.get("bets", []):
                        bet_id = bet.get("id")
                        # Filtra solo i mercati che ci interessano: 1=1X2, 5=Over/Under, 8=BTTS
                        if bet_id not in [1, 5, 8]:
                            continue
                            
                        for v in bet.get("values", []):
                            try:
                                price = float(v.get("odd"))
                                label = v.get("value", "").replace(' ', '_')
                                key = f"{fid}_{bet_id}_{label}"
                                old = state.get(key)

                                # Logica di confronto (solo se non è il primo avvio)
                                if old and old > 0 and not first_run:
                                    drop = ((old - price) / old) * 100
                                    # Alert se calo >= 10%
                                    if drop >= 10:
                                        alerts.append(
                                            f"📉 <b>{v['value']}</b>\n"
                                            f"{home} vs {away}\n"
                                            f"({league})\n"
                                            f"{old:.2f} → {price:.2f} ({drop:.1f}%↓)\n"
                                            f"⏰ {italy_time}"
                                        )

                                # Aggiorna stato
                                state[key] = price
                                processed += 1
                            except (ValueError, TypeError):
                                continue
                except Exception as e:
                    logging.error(f"⚠️ Errore processing partita {m.get('fixture',{}).get('id')}: {e}")

        except Exception as e:
            logging.error(f"❌ Errore critico {date}: {e}")

    # Salva lo stato aggiornato
    save_state(state)
    
    # Invio alert
    if alerts:
        msg = "🚨 <b>ALERT DROP QUOTE</b>\n\n" + "\n\n".join(alerts[:10])
        send_telegram(msg)
        logging.info(f"🚨 Inviati {len(alerts)} alert su Telegram")
    else:
        logging.info(f"ℹ️ Nessun drop su {processed} quote elaborate")
    
    logging.info("🔄 Ciclo completato.")

if __name__ == "__main__":
    run()
