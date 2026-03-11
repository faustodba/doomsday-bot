# ==============================================================================
#  DOOMSDAY BOT V5 - raccolta.py V5.12
#
# V5.12: Blacklist transazionale (reserve/commit/rollback) + TTL invariato 120s (commit)
# - RESERVED (TTL breve) durante invio; COMMITTED (TTL 120s) dopo conferma contatore
# - Rollback immediato se la marcia non parte (evita nodo bloccato in blacklist e attese inutili)
#
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
    """Pulisce nodi scaduti e verifica se chiave_nodo è in blacklist.

    Formato blacklist (V5.12):
      - chiave: "X_Y"
      - valore: {"ts": float, "state": "RESERVED"|"COMMITTED"}

    Retrocompatibilità:
      - valore float/int → COMMITTED
    """
    if blacklist is None or blacklist_lock is None:
        return False

    with blacklist_lock:
        ora = time.time()
        scadute = []

        for k, v in list(blacklist.items()):
            if isinstance(v, (int, float)):
                state = "COMMITTED"
                ts = float(v)
            elif isinstance(v, dict):
                state = v.get("state", "COMMITTED")
                ts = float(v.get("ts", 0))
            else:
                scadute.append(k)
                continue

            ttl = BLACKLIST_COMMITTED_TTL if state == "COMMITTED" else BLACKLIST_RESERVED_TTL
            if ora - ts > ttl:
                scadute.append(k)

        for k in scadute:
            blacklist.pop(k, None)

        return chiave_nodo in blacklist

def _blacklist_reserve(blacklist, blacklist_lock, chiave_nodo):
    """Prenota un nodo in stato RESERVED (TTL breve)."""
    if blacklist is None or blacklist_lock is None or not chiave_nodo:
        return
    with blacklist_lock:
        blacklist[chiave_nodo] = {"ts": time.time(), "state": "RESERVED"}


def _blacklist_commit(blacklist, blacklist_lock, chiave_nodo):
    """Conferma un nodo in stato COMMITTED (TTL=BLACKLIST_COMMITTED_TTL)."""
    if blacklist is None or blacklist_lock is None or not chiave_nodo:
        return
    with blacklist_lock:
        blacklist[chiave_nodo] = {"ts": time.time(), "state": "COMMITTED"}


def _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo):
    """Rilascia un nodo dalla blacklist (rollback immediato)."""
    if blacklist is None or blacklist_lock is None or not chiave_nodo:
        return
    _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)


def _tap_invia_squadra(porta, tipo, n_truppe, nome, squadra, tentativo, ciclo,
                       logger=None, blacklist=None, blacklist_lock=None):
    """
    Cerca nodo, verifica blacklist, tap nodo e invia squadra.

    Ritorna: (chiave_nodo, nodo_bloccato, marcia_inviata)
      chiave_nodo:    stringa "X_Y" del nodo prenotato, oppure None
      nodo_bloccato:  True se il gioco continua a proporre un nodo in blacklist
      marcia_inviata: True se il tap MARCIA è stato eseguito (anche se squadra respinta)
                      False se errore prima di MARCIA (blacklist va rilasciata dal chiamante)
    """
    def log(msg):
        if logger: logger(nome, msg)

    chiave_nodo = None

    # --- FASE 1: CERCA → leggi coordinate → verifica blacklist ---
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
    else:
        in_blacklist = _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo)

        if in_blacklist:
            log(f"Nodo ({cx},{cy}) in blacklist - riprovo CERCA")
            debug.salva_screen(screen_nodo, nome, "fase3_blacklist", squadra, tentativo,
                               f"{cx}_{cy}_r1")
            chiave_primo = chiave_nodo

            # Retry immediato: lente+tipo+CERCA
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
                    log(f"Nodo ({chiave_primo}) ancora bloccato dopo attesa - abbandono tipo {tipo}")
                    debug.salva_screen(screen_nodo, nome, "fase3_blacklist_bloccato",
                                       squadra, tentativo, chiave_primo)
                    adb.keyevent(porta, "KEYCODE_BACK")
                    time.sleep(0.5)
                    return None, True, False  # nodo_bloccato

            # Verifica che il nuovo nodo non sia anch'esso in blacklist
            if chiave_nodo and _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo):
                log(f"Anche il nuovo nodo ({cx},{cy}) è in blacklist - abbandono")
                adb.keyevent(porta, "KEYCODE_BACK")
                time.sleep(0.5)
                return None, True, False  # nodo_bloccato

        # --- FASE 4: nodo libero — tap nodo + prenota blacklist ---
        log(f"[FASE4] Nodo ({cx},{cy}) libero - tap nodo")
        adb.tap(porta, config.TAP_NODO)
        time.sleep(0.8)

        screen_popup = adb.screenshot(porta)
        debug.salva_screen(screen_popup, nome, "fase4_popup_raccogli", squadra, tentativo,
                           f"{cx}_{cy}")

        # Prenota in blacklist subito dopo tap nodo
        if blacklist is not None and blacklist_lock is not None and chiave_nodo:
            _blacklist_reserve(blacklist, blacklist_lock, chiave_nodo)

            log(f"Nodo ({cx},{cy}) prenotato in blacklist (RESERVED)")

    # --- FASE 5: RACCOGLI → SQUADRA → (truppe) → MARCIA ---
    # Se qualcosa va storto qui, il chiamante rilascia la blacklist (marcia_inviata=False)
    try:
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
        return chiave_nodo, False, True   # marcia_inviata=True
    except Exception as e:
        log(f"Errore durante sequenza RACCOGLI→MARCIA: {e}")
        return chiave_nodo, False, False  # marcia_inviata=False → chiamante rilascia blacklist

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
        # Fallback: contatore squadre non visibile → uso max_squadre come totale slot previsto

        # Nota: max_squadre arriva da config per istanza (tipicamente 4 o 5) e per tua scelta coincide con gli slot da riempire

        fallback_totale = max_squadre if max_squadre and max_squadre > 0 else 4

        log(f"Contatore non visibile dopo retry - assumo 0/{fallback_totale} attive, {fallback_totale} libere")

        attive_inizio, totale, libere = 0, fallback_totale, fallback_totale
    else:
        log(f"Squadre: {attive_inizio}/{totale} attive, {libere} libere")

    if libere == 0:
        log("Nessuna squadra libera - salto raccolta")
        stato.vai_in_home(porta, nome, logger)
        return 0

    obiettivo     = totale  # vogliamo sempre riempire tutti gli slot
    da_inviare    = libere if max_squadre == 0 else min(libere, max_squadre)
    log(f"Obiettivo: {obiettivo}/{totale} (da inviare: {da_inviare})")
    _status.istanza_target(nome, da_inviare)

    inviate            = 0
    fallimenti_cons    = 0   # fallimenti consecutivi — reset ad ogni successo
    MAX_FALLIMENTI     = 3   # max fallimenti consecutivi prima di abbandonare
    tipi_bloccati      = set()
    squadra_n          = 0   # contatore squadre tentate

    # Lettura reale attive — aggiornata dopo ogni MARCIA
    attive_correnti = attive_inizio

    for i in range(da_inviare):
        tipo = sequenza[i % len(sequenza)]
        squadra_n += 1

        # Se tipo bloccato da blacklist, salta
        if tipo in tipi_bloccati:
            log(f"Squadra {squadra_n} -> {tipo} saltata (tipo bloccato da blacklist)")
            continue

        # Abbandona se troppi fallimenti consecutivi
        if fallimenti_cons >= MAX_FALLIMENTI:
            log(f"Troppi fallimenti consecutivi ({fallimenti_cons}) - abbandono raccolta")
            break

        log(f"Invio squadra {squadra_n}/{da_inviare} -> {tipo} (fallimenti cons: {fallimenti_cons}/{MAX_FALLIMENTI})")

        chiave_nodo, nodo_bloccato, marcia_inviata = _tap_invia_squadra(
            porta, tipo, n_truppe, nome, squadra_n, 1, ciclo,
            logger, blacklist, blacklist_lock)

        # Se errore prima di MARCIA → rilascia blacklist
        if not marcia_inviata and chiave_nodo:
            log(f"Marcia non inviata - rilascio blacklist nodo {chiave_nodo}")
            if blacklist is not None and blacklist_lock is not None:
                _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)

        if nodo_bloccato:
            log(f"Tipo '{tipo}' bloccato da blacklist - squadre successive dello stesso tipo saltate")
            _log.registra_evento(ciclo, nome, "squadra_abbandonata", squadra_n, 1,
                                 f"tipo={tipo} nodo_bloccato")
            tipi_bloccati.add(tipo)
            fallimenti_cons += 1
            continue

        if not marcia_inviata:
            log(f"Errore invio squadra {squadra_n} - conto come fallimento")
            _log.registra_evento(ciclo, nome, "squadra_abbandonata", squadra_n, 1, "marcia_non_inviata")
            fallimenti_cons += 1
            continue

        # --- Post MARCIA: attendi e rileggi contatore reale ---
        delay = min(DELAY_POSTMARCIA_BASE, MAX_DELAY_POSTMARCIA)
        time.sleep(delay)

        s_post, screen_post = stato.back_rapidi_e_stato(porta, logger=logger, nome=nome)

        if s_post == "mappa":
            time.sleep(1.5)
        elif s_post == "home":
            log("Post-BACK: in home - torno in mappa")
            if not stato.vai_in_mappa(porta, nome, logger):
                log("Impossibile tornare in mappa - abbandono istanza")
                _log.registra_evento(ciclo, nome, "errore_mappa", squadra_n, 1, "post_back_home_no_mappa")
                stato.vai_in_home(porta, nome, logger)
                return inviate
            _, screen_post = stato.rileva(porta)
            time.sleep(1.5)
        else:
            log(f"Post-BACK: stato '{s_post}' inatteso - reset")
            _reset_stato(porta, nome, screen_post, squadra_n, 1, ciclo, logger)
            # Rilascia blacklist — marcia non confermata
            if chiave_nodo and blacklist is not None and blacklist_lock is not None:
                _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)
                log(f"Stato inatteso - rilascio blacklist nodo {chiave_nodo}")
            if not stato.vai_in_mappa(porta, nome, logger):
                log("Impossibile tornare in mappa - abbandono")
                stato.vai_in_home(porta, nome, logger)
                return inviate
            fallimenti_cons += 1
            continue

        # Lettura reale contatore dopo MARCIA
        screen_post = adb.screenshot(porta)
        debug.salva_screen(screen_post, nome, "post_marcia", squadra_n, 1)
        debug.salva_crop_ocr(screen_post, nome, "post_marcia", squadra_n, 1)

        attive_dopo, _, _ = stato.conta_squadre(porta, n_letture=3)

        if attive_dopo == -1:
            log(f"OCR non disponibile dopo MARCIA - conto come fallimento")
            debug.salva_screen(screen_post, nome, "ocr_fail", squadra_n, 1)
            _log.registra_evento(ciclo, nome, "ocr_fail", squadra_n, 1, "post_marcia")
            _status.istanza_ocr_fail(nome)
            fallimenti_cons += 1

        elif attive_dopo > attive_correnti:
            # Contatore aumentato → squadra confermata
            log(f"Squadra confermata ({attive_correnti} -> {attive_dopo})")
            debug.salva_crop_ocr(screen_post, nome, "ocr_ok", squadra_n, 1)
            _log.registra_evento(ciclo, nome, "squadra_ok", squadra_n, 1, f"attive={attive_dopo}")
            _status.istanza_squadra_ok(nome)
            attive_correnti = attive_dopo
            inviate += 1
            fallimenti_cons = 0  # reset fallimenti consecutivi

        else:
            # Contatore invariato o diminuito → squadra respinta o dinamica di gioco
            # Rileggi dopo 3s per distinguere ritardo UI da respinta reale
            log(f"Contatore invariato dopo MARCIA: attive={attive_dopo} (era {attive_correnti}) - rileggo tra 3s")
            debug.salva_screen(screen_post, nome, "cnt_errato", squadra_n, 1,
                               f"era{attive_correnti}_letto{attive_dopo}")
            _log.registra_evento(ciclo, nome, "cnt_errato", squadra_n, 1,
                                 f"era={attive_correnti} letto={attive_dopo}")
            _status.istanza_cnt_errato(nome)
            time.sleep(3.0)
            attive_dopo2, _, _ = stato.conta_squadre(porta, n_letture=3)

            if attive_dopo2 != -1 and attive_dopo2 > attive_correnti:
                # Era ritardo UI — squadra confermata
                log(f"Squadra confermata dopo retry ({attive_correnti} -> {attive_dopo2})")
                _log.registra_evento(ciclo, nome, "squadra_ok", squadra_n, 1,
                                     f"attive={attive_dopo2} (retry)")
                _status.istanza_squadra_ok(nome)
                attive_correnti = attive_dopo2
                inviate += 1
                fallimenti_cons = 0
            else:
                # Squadra respinta o dinamica esterna — aggiorna comunque il contatore reale
                attive_reali = attive_dopo2 if attive_dopo2 != -1 else attive_correnti
                log(f"Squadra respinta o dinamica esterna - attive reali: {attive_reali}")
                _log.registra_evento(ciclo, nome, "nodo_occupato", squadra_n, 1,
                                     f"attive_reali={attive_reali}")
                # Rilascia blacklist — la squadra non è partita
                if chiave_nodo and blacklist is not None and blacklist_lock is not None:
                    _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)
                    log(f"Squadra respinta - rilascio blacklist nodo {chiave_nodo}")
                attive_correnti = attive_reali
                fallimenti_cons += 1

    stato.vai_in_home(porta, nome, logger)
    log(f"Raccolta completata - {inviate}/{da_inviare} squadre inviate")
    _log.registra_evento(ciclo, nome, "completata", dettaglio=f"inviate={inviate}/{da_inviare}")
    return inviate