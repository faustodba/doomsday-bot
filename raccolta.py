# ==============================================================================
# DOOMSDAY BOT V5 - raccolta.py V5.13
# ==============================================================================
#
# V5.13: Fix logica invio marce + robustezza UI/contatore
# - Loop invio non è più "for N tentativi": continua finché gli slot risultano pieni (attive >= obiettivo)
#   o finché si raggiunge la soglia di fallimenti consecutivi.
# - OCR post-MARCIA: se il contatore non è leggibile (-1) non conta subito come fallimento;
#   esegue retry + recovery leggera per ridurre falsi negativi.
# - Sequenza RACCOGLI→SQUADRA→MARCIA: aggiunto controllo "schermata bloccata" (resta sulla maschera)
#   tramite confronto screenshot prima/dopo MARCIA; se non cambia, retry e/o rollback.
# - Blacklist transazionale stabile:
#   RESERVED (TTL breve) durante la transazione UI; COMMITTED (TTL 120s) solo dopo conferma contatore.
#   NOTA: per scelta attuale, il nodo COMMITTED NON viene rilasciato subito dopo conferma (resta occupato).
# - Fix bug critico: _blacklist_rollback non deve richiamare se stessa (ricorsione infinita).
#
# IMPORTANT: in questa fase BLACKLIST_COMMITTED_TTL resta fisso a 120s (stima percorrenza).
# In step successivi potremo leggere il tempo reale dalla maschera "Marcia".
# ==============================================================================

import hashlib
import time

import adb
import stato
import ocr
import debug
import log as _log
import status as _status
import config

DELAY_POSTMARCIA_BASE = config.DELAY_MARCIA / 1000
MAX_DELAY_POSTMARCIA = 6.0

# ------------------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------------------

def _md5_file(path: str) -> str:
    """Ritorna md5 del file (stringa esadecimale) o '' se fallisce."""
    try:
        h = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def _reset_stato(porta, nome, screen_path="", squadra=0, tentativo=0, ciclo=0, logger=None):
    def log(msg):
        if logger:
            logger(nome, msg)

    log("Reset stato - BACK rapidi e torno in home")
    if screen_path:
        debug.salva_screen(screen_path, nome, "reset", squadra, tentativo)
    _log.registra_evento(ciclo, nome, "reset", squadra, tentativo)

    stato.back_rapidi_e_stato(porta, logger=logger, nome=nome)
    stato.vai_in_home(porta, nome, logger, conferme=3)
    time.sleep(1.0)


# ------------------------------------------------------------------------------
# Blacklist transazionale (RESERVED / COMMITTED)
# ------------------------------------------------------------------------------

BLACKLIST_COMMITTED_TTL = 120  # secondi — TTL nodo occupato dopo conferma marcia (stima percorrenza)
BLACKLIST_RESERVED_TTL = 45    # secondi — TTL prenotazione temporanea durante transazione UI
# Retrocompatibilità: BLACKLIST_TTL era usato come unico TTL. Ora equivale al TTL COMMITTED.
BLACKLIST_TTL = BLACKLIST_COMMITTED_TTL
BLACKLIST_ATTESA_NODO = BLACKLIST_COMMITTED_TTL  # attesa massima quando il gioco ripropone nodo COMMITTED


def _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo) -> bool:
    """Pulisce nodi scaduti e verifica se chiave_nodo è in blacklist.

    Formato (V5.12+):
      - chiave: "X_Y" (es. "712_535")
      - valore: dict {"ts": float, "state": "RESERVED"|"COMMITTED"}

    Retrocompatibilità:
      - valore float/int → trattato come COMMITTED (ts=valore)

    Ritorna True se chiave_nodo è presente (non scaduto).
    """
    if blacklist is None or blacklist_lock is None or not chiave_nodo:
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
    with blacklist_lock:
        blacklist.pop(chiave_nodo, None)


def _blacklist_get_state(blacklist, blacklist_lock, chiave_nodo):
    """Ritorna lo stato del nodo in blacklist: RESERVED/COMMITTED oppure None."""
    if blacklist is None or blacklist_lock is None or not chiave_nodo:
        return None
    with blacklist_lock:
        v = blacklist.get(chiave_nodo)
    if isinstance(v, dict):
        return v.get("state")
    if isinstance(v, (int, float)):
        return "COMMITTED"
    return None


# ------------------------------------------------------------------------------
# Raccolta: ricerca nodo + OCR coordinate
# ------------------------------------------------------------------------------

def _cerca_nodo(porta, tipo):
    """Esegue LENTE → CAMPO/SEGHERIA × 2 → CERCA."""
    adb.tap(porta, config.TAP_LENTE)
    if tipo == "campo":
        adb.tap(porta, config.TAP_CAMPO)
        adb.tap(porta, config.TAP_CAMPO)
    else:
        adb.tap(porta, config.TAP_SEGHERIA)
        adb.tap(porta, config.TAP_SEGHERIA)
    time.sleep(0.5)
    adb.tap(
        porta,
        config.TAP_CERCA_CAMPO if tipo == "campo" else config.TAP_CERCA_SEGHERIA,
        delay_ms=config.DELAY_CERCA,
    )


def _leggi_coord_nodo(porta, nome, tipo, squadra, tentativo, retry_n, logger):
    """Tap lente coord + screenshot + OCR coordinate. Ritorna (chiave, cx, cy, screen)."""
    def log(msg):
        if logger:
            logger(nome, msg)

    time.sleep(1.5)
    adb.tap(porta, config.TAP_LENTE_COORD, delay_ms=1300)
    screen_nodo = adb.screenshot(porta)

    debug.salva_screen(screen_nodo, nome, f"fase3_popup_{tipo}", squadra, tentativo, f"r{retry_n}")
    debug.salva_crop_coord(screen_nodo, nome, "fase3_ocr_coord", squadra, tentativo, f"r{retry_n}")

    coord = ocr.leggi_coordinate_nodo(screen_nodo)
    log(f"[FASE3] OCR coordinate: {coord} (retry {retry_n})")

    if coord is None:
        return None, None, None, screen_nodo

    cx, cy = coord
    return f"{cx}_{cy}", cx, cy, screen_nodo


# ------------------------------------------------------------------------------
# Conferma contatore post-MARCIA (robusto)
# ------------------------------------------------------------------------------

def _leggi_attive_con_retry(porta, nome, logger=None, n_letture=3, retry=3, sleep_s=1.5):
    """Legge attive con retry quando OCR non disponibile (-1). Ritorna attive o -1."""
    def log(msg):
        if logger:
            logger(nome, msg)

    for i in range(retry):
        attive, _, _ = stato.conta_squadre(porta, n_letture=n_letture)
        if attive != -1:
            return attive
        log(f"OCR contatore non disponibile (tentativo {i+1}/{retry}) - attendo {sleep_s:.1f}s")
        time.sleep(sleep_s)
        # recovery leggera: un BACK singolo può chiudere micro-overlay e far tornare il contatore
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(0.6)
    return -1


# ------------------------------------------------------------------------------
# Sequenza UI: RACCOGLI → SQUADRA → (truppe) → MARCIA
# ------------------------------------------------------------------------------

def _esegui_marcia(porta, nome, n_truppe, squadra, tentativo, logger=None):
    """Esegue la sequenza di invio. Ritorna True se il tap MARCIA ha verosimilmente cambiato schermata."""
    def log(msg):
        if logger:
            logger(nome, msg)

    # 1) RACCOGLI
    adb.tap(porta, config.TAP_RACCOGLI)
    time.sleep(0.4)

    # 2) SQUADRA (entra nella maschera di creazione)
    adb.tap(porta, config.TAP_SQUADRA)
    time.sleep(1.2)

    # Screenshot "pre" (serve anche a capire se restiamo bloccati sulla maschera)
    screen_pre = adb.screenshot(porta)
    debug.salva_screen(screen_pre, nome, "pre_marcia", squadra, tentativo)
    pre_hash = _md5_file(screen_pre)

    # 3) Imposta truppe se richiesto
    if n_truppe and n_truppe > 0:
        adb.tap(porta, config.TAP_CANCELLA)
        time.sleep(0.4)
        adb.tap(porta, config.TAP_CAMPO_TESTO)
        time.sleep(0.4)
        # Nota: alcuni keycode potrebbero non funzionare in tutte le tastiere Android, ma manteniamo il tuo flusso.
        adb.keyevent(porta, "KEYCODE_CTRL_A")
        time.sleep(0.15)
        adb.keyevent(porta, "KEYCODE_DEL")
        time.sleep(0.15)
        adb.input_text(porta, str(n_truppe))
        time.sleep(0.25)
        adb.tap(porta, config.TAP_OK_TASTIERA)
        time.sleep(0.25)

    # 4) MARCIA
    adb.tap(porta, config.TAP_MARCIA)
    # attesa minima post tap
    time.sleep(0.8)

    # 5) Verifica che la UI sia cambiata: se identica spesso significa che siamo rimasti bloccati sulla maschera
    screen_post = adb.screenshot(porta)
    post_hash = _md5_file(screen_post)

    if pre_hash and post_hash and pre_hash == post_hash:
        log("MARCIA: schermata invariata (probabile maschera bloccata) - retry tap MARCIA")
        # Retry: a volte il primo tap non passa per overlay/lag
        adb.tap(porta, config.TAP_MARCIA)
        time.sleep(1.0)
        screen_post2 = adb.screenshot(porta)
        post_hash2 = _md5_file(screen_post2)
        if pre_hash and post_hash2 and pre_hash == post_hash2:
            log("MARCIA: ancora schermata invariata dopo retry - considero invio FALLITO")
            return False

    return True


# ------------------------------------------------------------------------------
# Invio squadra: cerca nodo + gestisci blacklist + invio
# ------------------------------------------------------------------------------

def _tap_invia_squadra(porta, tipo, n_truppe, nome, squadra, tentativo, ciclo,
                      logger=None, blacklist=None, blacklist_lock=None):
    """Ritorna (chiave_nodo, nodo_bloccato, marcia_tentata)."""
    def log(msg):
        if logger:
            logger(nome, msg)

    # --- FASE 1: CERCA → coordinate → blacklist ---
    _cerca_nodo(porta, tipo)
    chiave_nodo, cx, cy, screen_nodo = _leggi_coord_nodo(porta, nome, tipo, squadra, tentativo, 1, logger)

    if chiave_nodo is None:
        # OCR coordinate fallito: esci dal popup e prova tap nodo senza blacklist
        log("Coordinate nodo non leggibili - procedo senza blacklist")
        debug.salva_screen(screen_nodo, nome, "fase3_ocr_coord_fail", squadra, tentativo, "r1")
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(0.4)
        adb.tap(porta, config.TAP_NODO)
        time.sleep(0.6)
        # Tentiamo comunque la marcia
        ok = _esegui_marcia(porta, nome, n_truppe, squadra, tentativo, logger)
        return None, False, ok

    # Se in blacklist: retry CERCA e attese solo per COMMITTED
    if _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo):
        log(f"Nodo ({cx},{cy}) in blacklist - riprovo CERCA")
        debug.salva_screen(screen_nodo, nome, "fase3_blacklist", squadra, tentativo, f"{cx}_{cy}_r1")

        chiave_primo = chiave_nodo
        _cerca_nodo(porta, tipo)
        chiave_nodo, cx, cy, screen_nodo = _leggi_coord_nodo(porta, nome, tipo, squadra, tentativo, 2, logger)

        if chiave_nodo == chiave_primo or chiave_nodo is None:
            # Nodo riproposto: attesa lunga solo se COMMITTED
            log(f"Gioco ripropone stesso nodo - attendo {BLACKLIST_ATTESA_NODO}s (solo se nodo COMMITTED)")
            attesa = 3
            if _blacklist_get_state(blacklist, blacklist_lock, chiave_primo) == "COMMITTED":
                attesa = BLACKLIST_ATTESA_NODO
            time.sleep(attesa)

            _cerca_nodo(porta, tipo)
            chiave_nodo, cx, cy, screen_nodo = _leggi_coord_nodo(porta, nome, tipo, squadra, tentativo, 3, logger)

            if chiave_nodo == chiave_primo or chiave_nodo is None:
                log(f"Nodo ({chiave_primo}) ancora bloccato dopo attesa - abbandono tipo {tipo}")
                debug.salva_screen(screen_nodo, nome, "fase3_blacklist_bloccato", squadra, tentativo, chiave_primo)
                adb.keyevent(porta, "KEYCODE_BACK")
                time.sleep(0.4)
                return None, True, False

        # Se anche il nuovo è in blacklist: abbandona
        if chiave_nodo and _blacklist_pulisci_e_verifica(blacklist, blacklist_lock, chiave_nodo):
            log(f"Anche il nuovo nodo ({cx},{cy}) è in blacklist - abbandono")
            adb.keyevent(porta, "KEYCODE_BACK")
            time.sleep(0.4)
            return None, True, False

    # --- FASE 4: nodo libero → tap nodo + reserve ---
    log(f"[FASE4] Nodo ({cx},{cy}) libero - tap nodo")
    adb.tap(porta, config.TAP_NODO)
    time.sleep(0.7)

    screen_popup = adb.screenshot(porta)
    debug.salva_screen(screen_popup, nome, "fase4_popup_raccogli", squadra, tentativo, f"{cx}_{cy}")

    _blacklist_reserve(blacklist, blacklist_lock, chiave_nodo)
    log(f"Nodo ({cx},{cy}) prenotato in blacklist (RESERVED)")

    # --- FASE 5: invio marcia con retry locale ---
    for t in range(1, config.MAX_TENTATIVI_RACCOLTA + 1):
        ok = _esegui_marcia(porta, nome, n_truppe, squadra, t, logger)
        if ok:
            return chiave_nodo, False, True

        # Retry: ripulisci leggermente e ritenta (es. overlay o maschera bloccata)
        log(f"MARCIA fallita (tentativo {t}/{config.MAX_TENTATIVI_RACCOLTA}) - recovery light")
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(0.8)

    return chiave_nodo, False, False


# ------------------------------------------------------------------------------
# Entry point: raccolta istanza
# ------------------------------------------------------------------------------

def raccolta_istanza(porta, nome, truppe=None, max_squadre=0, logger=None, ciclo=0,
                    blacklist=None, blacklist_lock=None):
    def log(msg):
        if logger:
            logger(nome, msg)

    n_truppe = truppe if truppe is not None else config.TRUPPE_RACCOLTA

    log("Inizio raccolta risorse")
    _status.istanza_raccolta(nome)

    # Messaggi + Alleanza (come da tua architettura)
    import messaggi as _msg
    _msg.raccolta_messaggi(porta, nome, logger)

    import alleanza as _all
    _all.raccolta_alleanza(porta, nome, logger)

    # Porta in mappa
    gia_in_mappa = stato.rileva(porta)[0] == "mappa"
    if not stato.vai_in_mappa(porta, nome, logger):
        log("Impossibile andare in mappa - salto")
        _log.registra_evento(ciclo, nome, "errore_mappa", dettaglio="vai_in_mappa fallito")
        return 0

    if gia_in_mappa:
        log("Attesa rendering mappa (già in mappa al caricamento)...")
        time.sleep(2.0)

    # Leggi risorse deposito (2 tentativi)
    screen = adb.screenshot(porta)
    risorse = ocr.leggi_risorse(screen)
    if risorse.get("pomodoro", -1) < 0 and risorse.get("legno", -1) < 0:
        log("OCR risorse: primo tentativo fallito, riprovo tra 2s...")
        time.sleep(2.0)
        screen = adb.screenshot(porta)
        risorse = ocr.leggi_risorse(screen)

    pomodoro = risorse.get("pomodoro", -1)
    legno = risorse.get("legno", -1)
    acciaio = risorse.get("acciaio", -1)
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

    # Leggi contatore squadre (con fallback)
    attive_inizio, totale, libere = stato.conta_squadre(porta, n_letture=3)
    if attive_inizio == -1:
        log("Contatore non visibile - attendo 2.5s e riprovo...")
        time.sleep(2.5)
        attive_inizio, totale, libere = stato.conta_squadre(porta, n_letture=3)

    if attive_inizio == -1:
        # Fallback: contatore non leggibile -> usa max_squadre come totale slot previsto (4 o 5)
        fallback_totale = max_squadre if max_squadre and max_squadre > 0 else 4
        log(f"Contatore non visibile dopo retry - assumo 0/{fallback_totale} attive, {fallback_totale} libere")
        attive_inizio, totale, libere = 0, fallback_totale, fallback_totale
    else:
        log(f"Squadre: {attive_inizio}/{totale} attive, {libere} libere")

    if libere == 0:
        log("Nessuna squadra libera - salto raccolta")
        stato.vai_in_home(porta, nome, logger)
        return 0

    obiettivo = totale  # riempiamo tutti gli slot
    log(f"Obiettivo: {obiettivo}/{totale} (slot da riempire fino a pieno)")

    inviate = 0
    fallimenti_cons = 0
    MAX_FALLIMENTI = 3
    tipi_bloccati = set()

    attive_correnti = attive_inizio
    idx_seq = 0

    # Loop FINCHÉ slot pieni (o fallimenti)
    max_iter = obiettivo * max(2, config.MAX_TENTATIVI_RACCOLTA) + 5
    iter_n = 0

    while attive_correnti < obiettivo and iter_n < max_iter:
        iter_n += 1
        tipo = sequenza[idx_seq % len(sequenza)]
        idx_seq += 1

        # Se tipo bloccato, salta
        if tipo in tipi_bloccati:
            log(f"Tipo '{tipo}' bloccato - skip")
            continue

        if fallimenti_cons >= MAX_FALLIMENTI:
            log(f"Troppi fallimenti consecutivi ({fallimenti_cons}) - abbandono raccolta")
            break

        squadra_n = attive_correnti + 1  # etichetta logica (non è un id reale)
        log(f"Invio squadra (attive={attive_correnti}/{obiettivo}) -> {tipo} (fallimenti cons: {fallimenti_cons}/{MAX_FALLIMENTI})")

        chiave_nodo, nodo_bloccato, marcia_tentata = _tap_invia_squadra(
            porta, tipo, n_truppe, nome, squadra_n, 1, ciclo,
            logger=logger, blacklist=blacklist, blacklist_lock=blacklist_lock
        )

        if nodo_bloccato:
            log(f"Tipo '{tipo}' bloccato da blacklist - squadre successive dello stesso tipo saltate")
            tipi_bloccati.add(tipo)
            fallimenti_cons += 1
            continue

        if not marcia_tentata:
            # rollback immediato: la marcia non è partita
            if chiave_nodo:
                log(f"Marcia NON partita - rollback blacklist nodo {chiave_nodo}")
                _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)
            fallimenti_cons += 1
            continue

        # Post MARCIA: attesa base (non oltre MAX)
        delay = min(DELAY_POSTMARCIA_BASE, MAX_DELAY_POSTMARCIA)
        time.sleep(delay)

        # BACK meno aggressivi: 3 back e stop se mappa
        s_post, _ = stato.back_rapidi_e_stato(porta, n=3, logger=logger, nome=nome)
        if s_post == "home":
            log("Post-BACK: in home - torno in mappa")
            if not stato.vai_in_mappa(porta, nome, logger):
                log("Impossibile tornare in mappa - abbandono istanza")
                return inviate
        elif s_post not in ("mappa", "home"):
            log(f"Post-BACK: stato '{s_post}' inatteso - reset")
            _reset_stato(porta, nome, "", squadra_n, 1, ciclo, logger)

        # Lettura contatore (robusta)
        attive_dopo = _leggi_attive_con_retry(porta, nome, logger=logger, retry=3, sleep_s=1.5)

        if attive_dopo == -1:
            # Non siamo riusciti a leggere: non posso dire se è partita o no. Considero fallimento e rollback RESERVED.
            log("OCR post-MARCIA ancora non disponibile - considero fallimento prudenziale")
            if chiave_nodo:
                _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)
            fallimenti_cons += 1
            continue

        if attive_dopo > attive_correnti:
            log(f"Squadra confermata ({attive_correnti} -> {attive_dopo})")
            if chiave_nodo:
                _blacklist_commit(blacklist, blacklist_lock, chiave_nodo)
                log(f"Nodo {chiave_nodo} -> COMMITTED (TTL={BLACKLIST_COMMITTED_TTL}s)")
            attive_correnti = attive_dopo
            inviate += 1
            fallimenti_cons = 0
            continue

        # contatore invariato: retry dopo 3s
        log(f"Contatore invariato dopo MARCIA: attive={attive_dopo} (era {attive_correnti}) - rileggo tra 3s")
        time.sleep(3.0)
        attive_dopo2 = _leggi_attive_con_retry(porta, nome, logger=logger, retry=2, sleep_s=1.0)

        if attive_dopo2 != -1 and attive_dopo2 > attive_correnti:
            log(f"Squadra confermata dopo retry ({attive_correnti} -> {attive_dopo2})")
            if chiave_nodo:
                _blacklist_commit(blacklist, blacklist_lock, chiave_nodo)
                log(f"Nodo {chiave_nodo} -> COMMITTED (TTL={BLACKLIST_COMMITTED_TTL}s)")
            attive_correnti = attive_dopo2
            inviate += 1
            fallimenti_cons = 0
            continue

        # fallimento reale: rollback
        log("Squadra respinta o marcia non partita - rollback nodo")
        if chiave_nodo:
            _blacklist_rollback(blacklist, blacklist_lock, chiave_nodo)
        fallimenti_cons += 1

    # chiusura
    stato.vai_in_home(porta, nome, logger)
    log(f"Raccolta completata - {inviate}/{obiettivo - attive_inizio} squadre inviate (attive finali stimate={attive_correnti}/{obiettivo})")
    _log.registra_evento(ciclo, nome, "completata", dettaglio=f"inviate={inviate} attive_finali={attive_correnti}/{obiettivo}")
    return inviate
