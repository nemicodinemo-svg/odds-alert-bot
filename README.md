# 📊 Odds Drop Alert Bot

Bot Python automatizzato su GitHub Actions che monitora le quote calcistiche di **Bet365** in tempo reale e invia alert su **Telegram** quando rileva cali significativi ("Drop").

## 🎯 Funzionalità Principali
- 🔄 **Esecuzione automatica:** Ogni ora (`0 * * * *`) via GitHub Actions Scheduler.
- 📅 **Copertura:** Partite di oggi e domani.
- 🎯 **Mercati monitorati:** 1X2 (Match Winner), BTTS (Sì), Over/Under 1.5 / 2.5 / 3.5.
- 🧠 **Logica Smart Drop:** Soglie differenziate per filtrare il rumore sulle quote alte.
- 💾 **Persistenza:** Salva lo storico quote in `odds_state.json` per confrontare i cicli.
- 📱 **Notifiche:** Alert formattati in HTML su Telegram (max 10 per messaggio).

## ⚙️ Configurazione Richiesta
Imposta questi **GitHub Secrets** (`Settings > Secrets and variables > Actions`):

| Secret | Descrizione |
| :--- | :--- |
| `API_FOOTBALL_KEY` | Chiave gratuita da [api-football.com](https://www.api-football.com/) |
| `TG_BOT_TOKEN` | Token del bot Telegram (creato con @BotFather) |
| `TG_CHAT_ID` | Il tuo ID utente Telegram (ottenuto con @userinfobot) |

## 🧠 Logica di Rilevamento Drop
Il bot confronta le nuove quote con quelle salvate nel ciclo precedente. Scatta l'alert **solo se la quota scende** oltre queste soglie:

| Mercato / Fascia di Quota | Soglia Richiesta |
| :--- | :--- |
| **BTTS & Over/Under** | Calo ≥ 10% |
| **1X2 Quote Basse (≤ 2.50)** | Calo ≥ 10% |
| **1X2 Quote Medie (2.51 - 4.00)** | Calo ≥ 12% **OPPURE** ≥ 0.30 assoluto |
| **1X2 Quote Alte (> 4.00)** | Calo ≥ 15% **E** ≥ 0.50 assoluto |

## 📂 Struttura del Progetto
