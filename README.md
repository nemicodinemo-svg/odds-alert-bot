# ⚽ Odds Alert Bot 📉

Bot Python per monitorare cali di quote scommesse (≥10%) e inviare alert su Telegram.

> **Architettura**: Proxy Cloudflare + GitHub Actions + API-Football + The Odds API

---

## 🏗️ Architettura del Sistema

┌─────────────────┐
│ cron-job.org │ (trigger ogni 30 min)
└────────┬────────┘
│ POST /dispatches
▼
┌─────────────────┐
│ GitHub Actions │ (esegue odds_monitor.py)
│ • Python 3.10 │
│ • requests │
└────────┬────────┘
│ GET
▼
┌─────────────────┐
│ Cloudflare Worker│ (Proxy con IP "trusted")
│ odds-proxy-v2 │
│ URL: https://...│
└────────┬────────┘
│ Fetch
┌────┴────┐
▼ ▼
┌────────┐ ┌─────────────┐
│API-Foot│ │The Odds API │
│ball │ │(Serie A) │
└────────┘ └─────────────┘


### ✅ Vantaggi di questa architettura:
- **Nessun blocco IP**: Le API vedono Cloudflare, non GitHub Actions
- **Scalabile**: Aggiungi nuove API senza modificare il bot Python
- **Gratis**: Tutti i servizi usati hanno piani free sufficienti
- **Modulare**: Raccolta dati separata dall'elaborazione

---

## 📁 Struttura del Repository

odds-alert-bot/
├── .github/workflows/
│ └── monitor.yml # GitHub Actions workflow
├── odds_monitor.py # Bot Python principale
├── odds_state.json # Stato delle quote (generato automaticamente)
├── odds_monitor.log # Log file (generato automaticamente)
├── README.md # Questo file
└── requirements.txt # (opzionale) dipendenze Python


---

## 🔑 Configurazione: Secrets di GitHub Actions

Vai su: `Settings → Secrets and variables → Actions`

| Secret | Valore | Descrizione |
|--------|--------|-------------|
| `PROXY_URL` | `https://odds-proxy-v2.nemicodinemo.workers.dev/` | URL del Cloudflare Worker (obbligatorio) |
| `TG_BOT_TOKEN` | `123456789:AAH...` | Token del bot Telegram (da @BotFather) |
| `TG_CHAT_ID` | `-123456789` | Chat ID dove inviare gli alert |

> ⚠️ **Non inserire più** `API_FOOTBALL_KEY` o `ODDS_API_KEY`: le chiavi sono nel Worker, non su GitHub!

---

## ☁️ Cloudflare Worker: odds-proxy-v2

### URL pubblico:

https://odds-proxy-v2.nemicodinemo.workers.dev/


### Codice del Worker (semplificato):
```javascript
export default {
  async fetch(request, env) {
    const API_FOOTBALL_KEY = "LA_TUA_CHIAVE";
    const ODDS_API_KEY = "LA_TUA_CHIAVE";
    const today = new Date().toISOString().split('T')[0];
    
    const [footballRes, oddsRes] = await Promise.all([
      fetch(`https://v3.football.api-sports.io/odds?date=${today}&bookmaker=8`, {
        headers: { "x-apisports-key": API_FOOTBALL_KEY }
      }),
      fetch(`https://api.the-odds-api.com/v4/sports/soccer_italy_serie_a/odds/?apiKey=${ODDS_API_KEY}&regions=eu&markets=h2h,totals,btts`)
    ]);
    
    return new Response(JSON.stringify({
      football: await footballRes.json(),
      the_odds: await oddsRes.json()
    }), { headers: { "content-type": "application/json" } });
  }
};

Come aggiornare il Worker:
Vai su Cloudflare Dashboard → Workers
Seleziona odds-proxy-v2
Clicca Edit code
Modifica e clicca Save → Deploy
Testa con il pulsante Visit
⏰ Automazione: cron-job.org
Configurazione del job:
Campo
Valore
URL
https://api.github.com/repos/nemicodinemo-svg/odds-alert-bot/actions/workflows/monitor.yml/dispatches
Method
POST
Headers
Authorization: Bearer github_pat_XXX
Accept: application/vnd.github.v3+json
Content-Type: application/json
Body
{"ref": "main"}
Schedule
*/30 * * * * (ogni 30 minuti)
Timezone
Europe/Rome
Come generare il GitHub Token:
GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
Generate new token → Scope: repo (tutto)
Copia il token e incollalo in cron-job.org
🤖 Bot Python: odds_monitor.py
Funzionalità:
Scarica dati dal Proxy Cloudflare (NON chiama API direttamente)
Estrae quote Bet365 da API-Football
Confronta con lo storico salvato in odds_state.json
Invia alert su Telegram se drop ≥10%
Logging su file + console
Log di esempio:


2026-05-20 00:46:54 | INFO | 🟢 Avvio Bot (Proxy Mode)...
2026-05-20 00:46:54 | INFO | 📡 Richiesta dati a: https://...
2026-05-20 00:46:54 | INFO | ✅ Ricevute 10 partite dal proxy
2026-05-20 00:46:54 | INFO | ℹ️ Nessun drop su 58 quote elaborate
2026-05-20 00:46:54 | INFO | 🔄 Ciclo completato.

🚨 ALERT DROP QUOTE

📉 <b>Home</b>
Juventus vs Milan
(Serie A)
2.10 → 1.85 (11.9%↓)
⏰ 20/05 20:45

🚀 Deploy Rapido (da zero)
1. Cloudflare Worker

# 1. Crea account su cloudflare.com (gratis)
# 2. Workers & Pages → Create Worker → odds-proxy-v2
# 3. Incolla il codice del Worker (vedi sopra)
# 4. Aggiungi API Key come costanti nel codice
# 5. Save → Deploy → copia l'URL pubblico

2. GitHub Secrets

# Settings → Secrets and variables → Actions
# Aggiungi: PROXY_URL, TG_BOT_TOKEN, TG_CHAT_ID

3. cron-job.org

# Crea job con configurazione sopra
# Attiva e testa con "Run now"

4. Test

# GitHub → Actions → Odds Monitor → Run workflow
# Controlla i log: deve finire con "🔄 Ciclo completato."

🔧 Troubleshooting
❌ "PROXY_URL mancante!"
Verifica che il secret PROXY_URL esista in GitHub Actions
Controlla che il workflow YAML passi l'env var:

env:
  PROXY_URL: ${{ secrets.PROXY_URL }}

❌ "0 partite ricevute"
Il Worker sta chiamando l'endpoint sbagliato (/fixtures invece di /odds)
Verifica che API-Football key sia valida e non sospesa
Controlla che ci siano partite oggi con quote Bet365
❌ "0 quote elaborate"
Le partite ricevute non hanno il campo bookmakers
Verifica l'output del Worker: deve contenere "bookmakers": [...]
API-Football free restituisce solo partite con quote disponibili
❌ GitHub Actions bloccato
Le API vedono IP Azure come "hosting" → usa SEMPRE il proxy Cloudflare
Non chiamare mai API direttamente da GitHub Actions
❌ Telegram non riceve alert
Verifica TG_BOT_TOKEN e TG_CHAT_ID
Assicurati che il bot sia stato aggiunto alla chat/gruppo
Controlla i log per errori di rete
📈 Limiti dei piani Free
Servizio
Limite
Frequenza sicura
API-Football
100 req/giorno
Ogni 30 min = 48 req ✅
The Odds API
500 req/mese
Ogni 2 ore = ~360 req/mese ✅
Cloudflare Workers
100k req/giorno
~48 req/giorno ✅
GitHub Actions
2000 min/mese
~1 min/run × 48/giorno = ~1440/mese ✅
🔮 Future Espansioni
Filtrare per leghe specifiche
Modifica il Worker per filtrare per league.id:


const ALLOWED_LEAGUES = [135, 2, 3, 848]; // Serie A, UCL, Premier, La Liga
const filtered = footballData.response.filter(m => 
  ALLOWED_LEAGUES.includes(m.league?.id)
);

Aggiungere più bookmaker
Estendi extract_odds() in Python per supportare più ID bookmaker:

BOOKMAKERS = {8: "Bet365", 11: "William Hill", 15: "Unibet"}

Dashboard web
Aggiungi un endpoint /dashboard al Worker che serve HTML con le quote.
Storico su Cloudflare KV
Salva le quote su Cloudflare KV per analisi storiche e grafici.
Multi-canale alert
Aggiungi email, Discord o webhook oltre a Telegram.
📞 Contatti & Risorse
API-Football: https://dashboard.api-football.com/
The Odds API: https://the-odds-api.com/
Cloudflare Workers: https://developers.cloudflare.com/workers/
GitHub Actions Docs: https://docs.github.com/en/actions
Telegram Bot API: https://core.telegram.org/bots/api
🏆 Progetto educativo – Creato per imparare Python, API, cloud e automazione.
"Da zero a sistema production-ready in una sessione!" 🚀


---

## ✅ Cosa fare ORA per non perdere nulla:

1. **Copia il README.md sopra** e salvalo nel tuo repo GitHub
2. **Crea un file `SETUP_NOTES.md`** con:
   - URL del tuo Worker: `https://odds-proxy-v2.nemicodinemo.workers.dev/`
   - Le tue API Key (in un file `.env` locale, MAI su GitHub!)
   - Screenshot delle configurazioni critiche
3. **Fai un backup locale** della cartella del progetto

---

**Ora puoi spegnere il PC tranquillo!** 🌙

Il sistema gira in automatico su cloud, e con il README aggiornato potrai riprendere in mano tutto in futuro, anche tra mesi.

Buonanotte e grazie per la fiducia! 🍕🇮🇹🚀

Se tornerai, basterà leggere il README e sarai di nuovo operativo in 5 minuti! 👋

