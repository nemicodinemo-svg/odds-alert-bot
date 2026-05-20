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
        football_data = data.get("football", {}).get("response", [])
        
        if not football_data:
            logging.warning("⚠️ Nessuna partita ricevuta (normale in orari notturni)")
            save_state({"matches": {}})
            return
        
        logging.info(f"✅ Ricevute {len(football_data)} partite")
        
        # 🔍 DEBUG: Mostra struttura PRIMA partita
        if football_data:
            first_match = football_data[0]
            logging.info("🔍 DEBUG - Struttura prima partita:")
            logging.info(f"   Chiavi principali: {list(first_match.keys())}")
            
            # Teams
            teams = first_match.get("teams", {})
            logging.info(f"   Teams dict: {teams}")
            logging.info(f"   Home team: {teams.get('home', {})}")
            logging.info(f"   Away team: {teams.get('away', {})}")
            
            # Fixture
            fixture = first_match.get("fixture", {})
            logging.info(f"   Fixture: {fixture}")
            
            # League
            league = first_match.get("league", {})
            logging.info(f"   League: {league}")
        
        # 2. Carica stato (match monitorati)
        state = load_state()
        matches = state.get("matches", {})
        
        alerts = []
        new_matches = 0
        active_matches = 0
        
        # 3. Processa partite attuali
        current_match_ids = set()
        
        for idx, match in enumerate(football_data[:3]):  # Solo prime 3 per non spammare
            try:
                fid = match.get("fixture", {}).get("id")
                if not fid:
                    continue
                
                current_match_ids.add(fid)
                
                # Estrai info partita con fallback multipli
                teams = match.get("teams", {})
                home_team = teams.get("home", {})
                away_team = teams.get("away", {})
                
                # Prova diversi modi per ottenere i nomi
                home = (home_team.get("name") or 
                       home_team.get("winner") or 
                       home_team.get("team") or
                       str(home_team))
                away = (away_team.get("name") or 
                       away_team.get("winner") or 
                       away_team.get("team") or
                       str(away_team))
                
                league = match.get("league", {}).get("name", "Unknown League")
                fixture_date = match.get("fixture", {}).get("date", "")
                italy_time = utc_to_italy(fixture_date)
                
                logging.info(f"   Match {idx+1}: {home} vs {away} @ {italy_time}")
                
                # Verifica se partita già iniziata
                if is_match_started(fixture_date):
                    if fid in matches:
                        logging.info(f"   ⏭️ Partita iniziata, rimossa")
                    continue  # Salta partite già iniziate
                
                active_matches += 1
                
                # Estrai quote
                current_odds = extract_odds(match)
                if not current_odds:
                    logging.info(f"   ⚠️ Nessuna quota Bet365 trovata")
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
                    for market, baseline_values in baseline_odds.items():
                        if market not in current_odds:
                            continue
                        
                        current_values = current_odds[market]
                        
                        if isinstance(baseline_values, dict):
                            for outcome, base_price in baseline_values.items():
                                if outcome not in current_values:
                                    continue
                                
                                current_price = current_values[outcome]
                                drop_pct = ((current_price - base_price) / base_price) * 100
                                
                                # 📉 ALERT DROP >= 10%
                                if drop_pct <= -10:
                                    alerts.append(
                                        f"📉 <b>{outcome}</b> ({market})\n"
                                        f"<b>{home} vs {away}</b>\n"
                                        f"({league})\n"
                                        f"📊 Baseline: {base_price:.2f}\n"
                                        f"📊 Attuale: {current_price:.2f}\n"
                                        f"🔻 Drop: {abs(drop_pct):.1f}%\n"
                                        f"⏰ {italy_time}"
                                    )
                                    logging.info(f"   🎯 DROP: {home} vs {away} - {outcome} {base_price:.2f}→{current_price:.2f}")
                        
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
                                    f"📊 Baseline: {base_price:.2f}\n"
                                    f"📊 Attuale: {current_price:.2f}\n"
                                    f"🔻 Drop: {abs(drop_pct):.1f}%\n"
                                    f"⏰ {italy_time}"
                                )
                                logging.info(f"   🎯 DROP: {home} vs {away} - {market} {base_price:.2f}→{current_price:.2f}")
                    
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
                    # Estrai percentuale drop
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
