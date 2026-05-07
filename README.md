# 📊 Odds Alert Bot (API-Football)

Bot Python automatizzato su GitHub Actions che monitora le quote delle scommesse sportive in tempo reale e invia alert su Telegram quando le quote scendono significativamente ("Drop").

## 🎯 Funzionalità Principali
- **Monitoraggio:** Segue le partite di calcio (Football) con quote aperte.
- **Bookmaker:** Si concentra esclusivamente su **Bet365** (ID: 8).
- **Mercati Tracciati:**
  - **1X2** (Match Winner) con logica "Smart Drop" per filtrare il rumore sulle quote alte.
  - **BTTS** (Both Teams To Score - Sì).
  - **Goals Over/Under** (Linee 1.5, 2.5, 3.5).
- **Frequenza:** Esecuzione automatica ogni **45 minuti**.
- **Alert:** Invia messaggio su Telegram se la quota scende oltre una soglia definita.

## ⚙️ Configurazione & Requisiti

### 🔑 GitHub Secrets (Impostare in Settings -> Secrets and variables -> Actions)
| Nome Variabile | Descrizione |
| :--- | :--- |
| `API_FOOTBALL_KEY` | Chiave API gratuita da [api-sports.io](https://dashboard.api-football.com/) (Limite: 100 req/giorno) |
| `TG_BOT_TOKEN` | Token del bot Telegram creato con @BotFather |
| `TG_CHAT_ID` | Il tuo ID utente Telegram (ottenuto con @userinfobot) |

### 📅 Cron Job (GitHub Actions)
Configurato in `.github/workflows/monitor.yml`:
- `cron: '*/45 * * * *'` → Gira ogni 45 minuti.
- Consuma circa **64 richieste/giorno** (ben entro il limite gratuito di 100).

##  Logica di Funzionamento ("Smart Drop")

Il bot salva lo stato delle quote in `odds_state.json` e confronta le nuove quote con quelle salvate.

**Soglie di Alert:**
1. **BTTS & Over/Under:** Scatta se il calo è **≥ 10%**.
2. **1X2 (Quote Basse ≤ 2.50):** Scatta se calo **≥ 10%**.
3. **1X2 (Quote Medie 2.51 - 4.00):** Scatta se calo **≥ 12%** OPPURE calo assoluto **≥ 0.30**.
4. **1X2 (Quote Alte > 4.00):** Scatta se calo **≥ 15%** E calo assoluto **≥ 0.50** (per evitare falsi allarmi su quote alte volatili).

## 📂 Struttura File
- `odds_monitor.py`: Il codice principale Python che interroga l'API e invia gli alert.
- `.github/workflows/monitor.yml`: Il file che dice a GitHub quando eseguire il bot.
- `odds_state.json`: File generato automaticamente per memorizzare le quote vecchie.

## 🚀 Come Riprendere o Modificare
- **Per cambiare frequenza:** Modifica la riga `cron` in `monitor.yml`.
- **Per aggiungere altri bookmaker:** Modifica `params={"bookmaker": "8"}` in `odds_monitor.py` (dove 8 è l'ID di Bet365).
- **Per aggiungere Sisal o altri:** Bisogna trovare l'ID del bookmaker nella documentazione API-Football e aggiungerlo al ciclo di controllo.

## 📝 Log e Debug
I log vengono salvati in `odds_monitor.log`. Scarica l'artefatto "odds-state" da GitHub Actions per leggerli.
