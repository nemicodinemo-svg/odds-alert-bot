# 📊 Odds Alert Bot

Bot per monitorare variazioni di quote su Bet365 e inviare alert su Telegram.

## 🎯 Funzionalità
- Monitora Over 2.5 e BTTS (Entrambe le squadre segnano)
- Alert Telegram solo per drop ≥12%
- Esecuzione automatica ogni 2 ore via GitHub Actions
- Filtra partite nelle prossime 24h

## 🔧 Configurazione
### Secrets richiesti (Settings → Secrets and variables → Actions):
| Nome | Valore |
|------|--------|
| `ODDS_API_KEY` | API key da the-odds-api.com |
| `TG_BOT_TOKEN` | Token da @BotFather |
| `TG_CHAT_ID` | Tuo ID da @userinfobot |

### File principali:
- `odds_monitor.py` → Script Python di monitoraggio
- `.github/workflows/monitor.yml` → Configurazione esecuzione automatica

## 🚀 Come modificare
1. Cambia `MIN_DROP_PERCENT = 12` in `odds_monitor.py` per soglia diversa
2. Modifica `MAX_LEAGUES = 12` per monitorare più/meno campionati
3. Aggiungi mercati in `markets: "totals,both_teams_to_score"`

## ⚠️ Limiti API gratuite
- the-odds-api.com: 500 richieste/mese
- Con polling ogni 2 ore + 12 campionati: ~360 richieste/mese ✅
- Se vedi errore 429: riduci campionati o aumenta intervallo

## 🛠️ Troubleshooting
| Problema | Soluzione |
|----------|-----------|
| Nessun alert | Primo giro normale, attendi secondo ciclo |
| Errore 429 | Rate limit API, il bot si riprende da solo |
| Job rosso | Controlla log in Actions → clicca sul job → "Annotations" |

## 📞 Supporto
Progetto creato con assistenza AI. Per modifiche future, consultare documentazione GitHub Actions e the-odds-api.com.
