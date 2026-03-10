# ==============================================================================
#  DOOMSDAY BOT V5 - raccolta.py  V5.6
# ==============================================================================

import time
import threading
import adb
import stato
import ocr
import debug
import log as _log
import status as _status
import config

DELAY_POSTMARCIA_BASE  = config.DELAY_MARCIA / 1000
DELAY_POSTMARCIA_EXTRA = 1.0
MAX_DELAY_POSTMARCIA   = 6.0
BACKOFF_SOGLIA_RESET   = 3

def _reset_stato(porta, nome, screen_path="", squadra=0, tentativo=0, ciclo=0, logger=None):
    def log(msg):
        if logger: logger(nome, msg)
    log("Reset stato - BACK rapidi e torno in home")
    if screen_path:
        debug.salva_screen(screen_path, nome, "reset", squadra, tentativo)
    _log.registra_evento(ciclo, nome, "reset", squadra, tentativo)
    stato.back_rapidi_e_stato(porta, logger=logger, nome=nome)
    stato.vai_in_home(porta, nome, logger, conferme=3)
    time.sleep(1.0)

BLACKLIST_TTL          = 120   # secondi — TTL nodo in blacklist (2 min fissi)
BLACKLIST_ATTESA_NODO  = 120   # secondi — attesa se il gioco ripropone stesso nodo in blacklist

def _cerca_nodo(porta, tipo):
    """Esegue LENTE → CAMPO/SEGHERIA × 2 → CERCA. Riutilizzabile per retry blacklist."""
    adb.tap(porta, config.TAP_LENTE)
    if tipo == "campo":
        adb.tap(porta, config.TAP_CAMPO); adb.tap(porta, config.TAP_CAMPO)
    else:
        adb.tap(porta, config.TAP_SEGHERIA); adb.tap(porta, config.TAP_SEGHERIA)
    time.sleep(0.5)
    adb.tap(porta,
            config.TAP_CERCA_CAMPO if tipo == "campo" else config.TAP_CERCA_SEGHERIA,
            delay_ms=config.DELAY_CERCA)

def _leggi_coord_nodo(porta, nome, tipo, squadra, tentativo, retry_n, logger):
    """
    Esegue tap lente piccola + screenshot + OCR coordinate.
    Ritorna (chiave_nodo, cx, cy, screen) oppure (None, None, None, screen) se OCR fallisce.
    """
    def log(msg):
        if logger: logger(nome, msg)

    time.sleep(1.5)
    adb.tap(porta, config.TAP_LENTE_COORD, delay_ms=1300)
    screen_nodo = adb.screenshot(porta)

    debug.salva_screen(screen_nodo, nome, f"fase3_popup_{tipo}", squadra, tentativo,
                       f"r{retry_n}")
    debug.salva_crop_coord(screen_nodo, nome, "fase3_ocr_coord", squadra, tentativo,
                           f"r{retry_n}")

    coord = ocr.leggi_coordinate_nodo(screen_nodo)
    log(f"[FASE3] OCR coordinate: {coord} (retry {retry_n})")

    if coord is None:
        return None, None, None, screen_nodo

    cx, cy = coord
    return f"{cx}_{cy}", cx, cy, screen_nodo

def _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo):
    """Pulisce nodi scaduti e verifica se chiave_nodo è in blacklist. Ritorna bool."""
    if blacklist is None or blacklist_lock is None:
        return False
    with blacklist_lock:
        ora = time.time()
        scadute = [k for k, t in blacklist.items() if ora - t > BLACKLIST_TTL]
        for k in scadute:
            del blacklist[k]
        return chiave_nodo in blacklist

def _tap_invia_squadra(porta, tipo, n_truppe, nome, squadra, tentativo, ciclo,
                       logger=None, blacklist=None, blacklist_lock=None):
    """
    Cerca nodo, verifica blacklist, tap nodo e invia squadra.

    Logica blacklist:
      1. CERCA → leggi coordinate nodo
      2. Se nodo in blacklist → riprova CERCA (lente+tipo+cerca)
      3. Se il gioco ripropone STESSO nodo → aspetta BLACKLIST_ATTESA_NODO secondi
      4. Riprova CERCA ancora una volta
      5. Se ancora stesso nodo → ritorna (chiave=None, nodo_bloccato=True)
      6. Se nodo diverso → procedi normalmente

    Ritorna: (chiave_nodo, nodo_bloccato)
      chiave_nodo:   stringa "X_Y" del nodo prenotato, oppure None
      nodo_bloccato: True se il gioco continua a proporre un nodo in blacklist
                     e non è possibile inviare la squadra
    """
    def log(msg):
        if logger: logger(nome, msg)

    chiave_nodo = None

    # --- FASE 1+2+3: CERCA → leggi coordinate → verifica blacklist ---
    _cerca_nodo(porta, tipo)
    chiave_nodo, cx, cy, screen_nodo = _leggi_coord_nodo(
        porta, nome, tipo, squadra, tentativo, 1, logger)

    if chiave_nodo is None:
        # OCR fallito — procedi senza blacklist
        log("Coordinate nodo non leggibili - procedo senza blacklist")
        debug.salva_screen(screen_nodo, nome, "fase3_ocr_coord_fail", squadra, tentativo, "r1")
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(0.5)
        adb.tap(porta, config.TAP_NODO)
        time.sleep(0.8)
        # Prenota placeholder in blacklist non possibile — procedi
        chiave_nodo = None
    else:
        in_blacklist = _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo)

        if in_blacklist:
            log(f"Nodo ({cx},{cy}) in blacklist - riprovo CERCA")
            debug.salva_screen(screen_nodo, nome, "fase3_blacklist", squadra, tentativo,
                               f"{cx}_{cy}_r1")
            chiave_primo = chiave_nodo

            # --- Retry immediato: lente+tipo+CERCA ---
            _cerca_nodo(porta, tipo)
            chiave_nodo, cx, cy, screen_nodo = _leggi_coord_nodo(
                porta, nome, tipo, squadra, tentativo, 2, logger)

            if chiave_nodo == chiave_primo or chiave_nodo is None:
                # Gioco ripropone stesso nodo — aspetta 2 minuti e riprova
                log(f"Gioco ripropone stesso nodo - attendo {BLACKLIST_ATTESA_NODO}s")
                time.sleep(BLACKLIST_ATTESA_NODO)

                _cerca_nodo(porta, tipo)
                chiave_nodo, cx, cy, screen_nodo = _leggi_coord_nodo(
                    porta, nome, tipo, squadra, tentativo, 3, logger)

                if chiave_nodo == chiave_primo or chiave_nodo is None:
                    # Ancora stesso nodo dopo attesa — segnala nodo bloccato
                    log(f"Nodo ({chiave_primo}) ancora bloccato dopo attesa - abbandono tipo {tipo}")
                    debug.salva_screen(screen_nodo, nome, "fase3_blacklist_bloccato",
                                       squadra, tentativo, chiave_primo)
                    # Chiudi popup con BACK
                    adb.keyevent(porta, "KEYCODE_BACK")
                    time.sleep(0.5)
                    return None, True   # nodo_bloccato=True

            # Nodo diverso trovato — verifica non sia anch'esso in blacklist
            in_blacklist2 = _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo)
            if in_blacklist2:
                log(f"Anche il nuovo nodo ({cx},{cy}) è in blacklist - abbandono")
                adb.keyevent(porta, "KEYCODE_BACK")
                time.sleep(0.5)
                return None, True

        # --- FASE 4: nodo libero — tap nodo ---
        log(f"[FASE4] Nodo ({cx},{cy}) libero - tap nodo")
        adb.tap(porta, config.TAP_NODO)
        time.sleep(0.8)

        screen_popup = adb.screenshot(porta)
        debug.salva_screen(screen_popup, nome, "fase4_popup_raccogli", squadra, tentativo,
                           f"{cx}_{cy}")

        # Prenota in blacklist
        if blacklist is not None and blacklist_lock is not None and chiave_nodo:
            with blacklist_lock:
                blacklist[chiave_nodo] = time.time()
                log(f"Nodo ({cx},{cy}) prenotato in blacklist")

    # Procedi con RACCOGLI → SQUADRA → (truppe) → MARCIA
    adb.tap(porta, config.TAP_RACCOGLI)
    adb.tap(porta, config.TAP_SQUADRA)
    time.sleep(1.5)
    if n_truppe > 0:
        adb.tap(porta, config.TAP_CANCELLA);      time.sleep(0.6)
        adb.tap(porta, config.TAP_CAMPO_TESTO);   time.sleep(0.6)
        adb.keyevent(porta, "KEYCODE_CTRL_A");     time.sleep(0.2)
        adb.keyevent(porta, "KEYCODE_DEL");        time.sleep(0.2)
        adb.input_text(porta, str(n_truppe));      time.sleep(0.4)
        adb.tap(porta, config.TAP_OK_TASTIERA);    time.sleep(0.4)
    screen_pre = adb.screenshot(porta)
    debug.salva_screen(screen_pre, nome, "pre_marcia", squadra, tentativo)
    adb.tap(porta, config.TAP_MARCIA)
    return chiave_nodo, False   # nodo_bloccato=False

def raccolta_istanza(porta, nome, truppe=None, max_squadre=0, logger=None, ciclo=0,
                     blacklist=None, blacklist_lock=None):
    def log(msg):
        if logger: logger(nome, msg)

    n_truppe = truppe if truppe is not None else config.TRUPPE_RACCOLTA
    log("Inizio raccolta risorse")
    _status.istanza_raccolta(nome)

    import messaggi as _msg
    _msg.raccolta_messaggi(porta, nome, logger)

    import alleanza as _all
    _all.raccolta_alleanza(porta, nome, logger)


    gia_in_mappa = stato.rileva(porta)[0] == "mappa"
    if not stato.vai_in_mappa(porta, nome, logger):
        log("Impossibile andare in mappa - salto")
        _log.registra_evento(ciclo, nome, "errore_mappa", dettaglio="vai_in_mappa fallito")
        return 0

    # Se era già in mappa (caricamento diretto) attendi rendering completo
    if gia_in_mappa:
        log("Attesa rendering mappa (già in mappa al caricamento)...")
        time.sleep(2.0)

    # Leggi risorse deposito — retry se OCR fallisce
    screen   = adb.screenshot(porta)
    risorse  = ocr.leggi_risorse(screen)
    if risorse.get("pomodoro", -1) < 0 and risorse.get("legno", -1) < 0:
        log("OCR risorse: primo tentativo fallito, riprovo tra 2s...")
        time.sleep(2.0)
        screen  = adb.screenshot(porta)
        risorse = ocr.leggi_risorse(screen)
    pomodoro = risorse.get("pomodoro", -1)
    legno    = risorse.get("legno",    -1)
    acciaio  = risorse.get("acciaio",  -1)
    petrolio = risorse.get("petrolio", -1)
    _status.istanza_risorse(nome, pomodoro, legno, acciaio, petrolio)

    if pomodoro > 0 and legno > 0:
        diff = legno - pomodoro
        log(f"Pomodoro: {pomodoro/1_000_000:.1f}M  Legno: {legno/1_000_000:.1f}M  Diff: {diff/1_000_000:+.1f}M")
        if abs(diff) > 5_000_000:
            tipo_carente = "campo" if diff > 0 else "segheria"
            log(f"Diff > 5M -> invio solo {tipo_carente}")
            sequenza = [tipo_carente] * 5
        else:
            log("Diff <= 5M -> alterno campo/segheria")
            sequenza = ["campo", "segheria", "campo", "segheria", "campo"]
    else:
        log("OCR risorse fallito - alterno campo/segheria")
        sequenza = ["campo", "segheria", "campo", "segheria", "campo"]

    attive_inizio, totale, libere = stato.conta_squadre(porta, n_letture=3)
    if attive_inizio == -1:
        log("Contatore non visibile - attendo 2.5s e riprovo...")
        time.sleep(2.5)
        attive_inizio, totale, libere = stato.conta_squadre(porta, n_letture=3)

    if attive_inizio == -1:
        log("Contatore non visibile dopo retry - assumo 0/4 attive, 4 libere")
        attive_inizio, totale, libere = 0, 4, 4
    else:
        log(f"Squadre: {attive_inizio}/{totale} attive, {libere} libere")

    if libere == 0:
        log("Nessuna squadra libera - salto raccolta")
        stato.vai_in_home(porta, nome, logger)
        return 0

    da_inviare    = libere if max_squadre == 0 else min(libere, max_squadre)
    attive_attese = attive_inizio
    log(f"Obiettivo: {attive_inizio + da_inviare}/{totale} (da inviare: {da_inviare})")
    _status.istanza_target(nome, da_inviare)

    inviate = 0
    tipi_bloccati = set()  # tipi per cui il nodo è bloccato — skip squadre successive dello stesso tipo

    for i in range(da_inviare):
        tipo     = sequenza[i % len(sequenza)]
        riuscita = False
        ocr_fail_consecutivi = 0

        # Se questo tipo è bloccato, salta direttamente
        if tipo in tipi_bloccati:
            log(f"Squadra {i+1}/{da_inviare} -> {tipo} saltata (tipo bloccato da blacklist)")
            continue

        for tentativo in range(1, config.MAX_TENTATIVI_RACCOLTA + 1):
            log(f"Invio squadra {i+1}/{da_inviare} -> {tipo} (tentativo {tentativo}/{config.MAX_TENTATIVI_RACCOLTA})")

            chiave_nodo, nodo_bloccato = _tap_invia_squadra(
                porta, tipo, n_truppe, nome, i+1, tentativo, ciclo,
                logger, blacklist, blacklist_lock)

            if nodo_bloccato:
                log(f"Tipo '{tipo}' bloccato da blacklist - squadre successive dello stesso tipo saltate")
                _log.registra_evento(ciclo, nome, "squadra_abbandonata", i+1, tentativo,
                                     f"tipo={tipo} nodo_bloccato")
                tipi_bloccati.add(tipo)
                riuscita = False
                break  # esce dal loop tentativi, continua con squadra successiva

            delay = min(DELAY_POSTMARCIA_BASE + ocr_fail_consecutivi * DELAY_POSTMARCIA_EXTRA,
                        MAX_DELAY_POSTMARCIA)
            if ocr_fail_consecutivi > 0:
                log(f"Delay post-MARCIA: {delay:.1f}s (fail precedenti: {ocr_fail_consecutivi})")
            time.sleep(delay)

            s_post, screen_post = stato.back_rapidi_e_stato(porta, logger=logger, nome=nome)

            if s_post == "mappa":
                time.sleep(1.5)
            elif s_post == "home":
                log("Post-BACK: in home - torno in mappa")
                if not stato.vai_in_mappa(porta, nome, logger):
                    log("Impossibile tornare in mappa - abbandono istanza")
                    _log.registra_evento(ciclo, nome, "errore_mappa", i+1, tentativo, "post_back_home_no_mappa")
                    stato.vai_in_home(porta, nome, logger)
                    return inviate
                _, screen_post = stato.rileva(porta)
                time.sleep(1.5)
            else:
                log(f"Post-BACK: stato '{s_post}' inatteso - reset")
                _reset_stato(porta, nome, screen_post, i+1, tentativo, ciclo, logger)
                if not stato.vai_in_mappa(porta, nome, logger):
                    log("Impossibile tornare in mappa - abbandono")
                    stato.vai_in_home(porta, nome, logger)
                    return inviate
                ocr_fail_consecutivi += 1
                continue

            screen_post = adb.screenshot(porta)
            debug.salva_screen(screen_post, nome, "post_marcia", i+1, tentativo)
            debug.salva_crop_ocr(screen_post, nome, "post_marcia", i+1, tentativo)

            attive_dopo, _, _ = stato.conta_squadre(porta, n_letture=3)

            if attive_dopo == -1:
                ocr_fail_consecutivi += 1
                log(f"OCR non disponibile dopo MARCIA (fail #{ocr_fail_consecutivi})")
                debug.salva_screen(screen_post, nome, "ocr_fail", i+1, tentativo, f"fail{ocr_fail_consecutivi}")
                debug.salva_crop_ocr(screen_post, nome, "ocr_fail", i+1, tentativo, f"fail{ocr_fail_consecutivi}")
                _log.registra_evento(ciclo, nome, "ocr_fail", i+1, tentativo, f"fail_consecutivi={ocr_fail_consecutivi}")
                _status.istanza_ocr_fail(nome)
                if ocr_fail_consecutivi >= BACKOFF_SOGLIA_RESET:
                    log(f"OCR-fail persistente ({ocr_fail_consecutivi}x) - reset completo")
                    _reset_stato(porta, nome, screen_post, i+1, tentativo, ciclo, logger)
                    if not stato.vai_in_mappa(porta, nome, logger):
                        log("Impossibile tornare in mappa - abbandono")
                        stato.vai_in_home(porta, nome, logger)
                        return inviate
                    ocr_fail_consecutivi = 0

            elif attive_dopo == attive_attese + 1:
                log(f"Squadra confermata ({attive_attese} -> {attive_dopo})")
                debug.salva_crop_ocr(screen_post, nome, "ocr_ok", i+1, tentativo)
                _log.registra_evento(ciclo, nome, "squadra_ok", i+1, tentativo, f"attive={attive_dopo}")
                _status.istanza_squadra_ok(nome)
                # Rimuovi nodo dalla blacklist — è occupato dalla nostra squadra, non serve più bloccare
                # Nodo rimane in blacklist per TTL fisso (BLACKLIST_TTL secondi).
                # NON viene rimosso alla conferma marcia: la squadra potrebbe
                # non essere ancora arrivata e la prossima ricerca potrebbe
                # selezionare lo stesso nodo prima dell'arrivo.
                attive_attese += 1
                inviate += 1
                ocr_fail_consecutivi = 0
                riuscita = True
                break

            else:
                log(f"Contatore errato: atteso {attive_attese+1}, letto {attive_dopo} - rileggo tra 3s")
                debug.salva_screen(screen_post, nome, "cnt_errato", i+1, tentativo, f"atteso{attive_attese+1}_letto{attive_dopo}")
                debug.salva_crop_ocr(screen_post, nome, "cnt_errato", i+1, tentativo, f"atteso{attive_attese+1}_letto{attive_dopo}")
                _log.registra_evento(ciclo, nome, "cnt_errato", i+1, tentativo, f"atteso={attive_attese+1} letto={attive_dopo}")
                _status.istanza_cnt_errato(nome)
                ocr_fail_consecutivi = 0

                # Retry lettura — distingue ritardo UI / nodo occupato / stato sfasato
                time.sleep(3.0)
                attive_dopo2, _, _ = stato.conta_squadre(porta, n_letture=3)

                if attive_dopo2 == attive_attese + 1:
                    # Era solo ritardo UI — squadra confermata
                    log(f"Squadra confermata dopo retry ({attive_attese} -> {attive_dopo2})")
                    _log.registra_evento(ciclo, nome, "squadra_ok", i+1, tentativo, f"attive={attive_dopo2} (retry)")
                    _status.istanza_squadra_ok(nome)
                    # Nodo rimane in blacklist per TTL — non rimuovere manualmente
                    attive_attese += 1
                    inviate += 1
                    riuscita = True
                    break

                elif attive_dopo2 == attive_attese:
                    # Squadra respinta (nodo occupato) — riprova senza reset completo
                    log(f"Squadra respinta (nodo occupato) - riprovo")
                    _log.registra_evento(ciclo, nome, "nodo_occupato", i+1, tentativo, f"attive={attive_dopo2}")
                    # Nodo rimane in blacklist per TTL — non rimuovere manualmente
                    # rimane in mappa, il loop continua al tentativo successivo

                else:
                    # Contatore davvero sfasato — reset completo
                    log(f"Contatore sfasato dopo retry: atteso {attive_attese+1}, letto {attive_dopo2} - reset")
                    if blacklist is not None and blacklist_lock is not None and chiave_nodo:
                        with blacklist_lock:
                            blacklist.pop(chiave_nodo, None)
                    _reset_stato(porta, nome, screen_post, i+1, tentativo, ciclo, logger)
                    if not stato.vai_in_mappa(porta, nome, logger):
                        log("Impossibile tornare in mappa - abbandono")
                        stato.vai_in_home(porta, nome, logger)
                        return inviate

        if not riuscita and tipo not in tipi_bloccati:
            log(f"Squadra {i+1} abbandonata dopo {config.MAX_TENTATIVI_RACCOLTA} tentativi")
            _log.registra_evento(ciclo, nome, "squadra_abbandonata", i+1, config.MAX_TENTATIVI_RACCOLTA, f"tipo={tipo}")

    stato.vai_in_home(porta, nome, logger)
    log(f"Raccolta completata - {inviate}/{da_inviare} squadre inviate")
    _log.registra_evento(ciclo, nome, "completata", dettaglio=f"inviate={inviate}/{da_inviare}")
    return inviate
