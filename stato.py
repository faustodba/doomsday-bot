# ==============================================================================
#  DOOMSDAY BOT V5 - stato.py
#  Rilevamento stato istanza: home / mappa / banner / sconosciuto
#
#  V5.3 - Fix blocco vai_in_mappa():
#    - Corretto bug variabile s2/s3 nel log finale
#    - Aggiunto terzo tentativo con delay più lungo (5s)
#    - Aggiunto MAX_TENTATIVI_MAPPA: garantisce uscita anche se il tap
#      non porta mai in mappa (evita loop infiniti in raccolta.py)
# ==============================================================================

import time
import adb
import ocr
import config

# --- Parametri BACK rapidi ---
N_BACK          = 5     # numero di BACK da inviare
DELAY_BACK      = 0.3   # secondi tra un BACK e il successivo
DELAY_POST_BACK = 0.5   # pausa stabilizzazione UI dopo l'ultimo BACK

# --- Massimo cicli di BACK per uscire da overlay persistente ---
MAX_CICLI_BACK  = 4     # max 4 × N_BACK = 20 BACK totali prima di arrendersi

# --- Massimo tentativi tap per vai_in_mappa ---
MAX_TENTATIVI_MAPPA = 3  # dopo 3 tap falliti → ritorna False con certezza

# ------------------------------------------------------------------------------
# Rileva stato corrente (senza screenshot: usa screen già scattato)
# ------------------------------------------------------------------------------
def rileva_screen(screen: str) -> str:
    """Rileva stato da screen già scattato. Ritorna 'home'|'mappa'|'overlay'|'sconosciuto'."""
    if not screen:
        return "sconosciuto"
    r, g, b = adb.leggi_pixel(screen, config.STATO_CHECK_X, config.STATO_CHECK_Y)
    if r == -1:
        return "sconosciuto"
    if r < config.STATO_SOGLIA_R:
        return "home"
    if r >= config.STATO_SOGLIA_R and (r + g + b) > 30:
        return "mappa"
    return "overlay"   # RGB < 30 = banner/schermo nero, o altro

# ------------------------------------------------------------------------------
# Rileva stato corrente (scatta screenshot)
# Ritorna (stato, screen_path)
# ------------------------------------------------------------------------------
def rileva(porta: str) -> tuple:
    """Scatta screenshot e rileva stato. Ritorna (stato, screen_path)."""
    screen = adb.screenshot(porta)
    if not screen:
        return ("sconosciuto", "")
    return (rileva_screen(screen), screen)

# ------------------------------------------------------------------------------
# Invia N BACK rapidi e legge lo stato risultante
# ------------------------------------------------------------------------------
def back_rapidi_e_stato(porta: str, n: int = N_BACK, logger=None, nome: str = "") -> tuple:
    """
    Invia n BACK a intervalli DELAY_BACK, poi legge lo stato.
    Ritorna (stato, screen_path).
    """
    def log(msg):
        if logger: logger(nome, msg)

    for i in range(n):
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(DELAY_BACK)
    time.sleep(DELAY_POST_BACK)

    s, screen = rileva(porta)
    log(f"Stato dopo {n} BACK: {s}")
    return (s, screen)

# ------------------------------------------------------------------------------
# Porta l'istanza in uno stato pulito (home o mappa) partendo da qualsiasi stato
# ------------------------------------------------------------------------------
def _pulisci_overlay(porta: str, nome: str, logger=None) -> str:
    """
    Cicli di N_BACK finché stato è home o mappa.
    Ritorna "home" | "mappa" | "fallito".
    """
    def log(msg):
        if logger: logger(nome, msg)

    for ciclo in range(MAX_CICLI_BACK):
        s, _ = back_rapidi_e_stato(porta, N_BACK, logger, nome)
        if s in ("home", "mappa"):
            return s
        log(f"Overlay persistente (ciclo {ciclo+1}/{MAX_CICLI_BACK}) - altro ciclo BACK")

    log(f"Impossibile uscire da overlay dopo {MAX_CICLI_BACK} cicli")
    return "fallito"

# ------------------------------------------------------------------------------
# Vai in mappa
# V5.3: fino a MAX_TENTATIVI_MAPPA tap, delay crescente, no loop infinito
# ------------------------------------------------------------------------------
def vai_in_mappa(porta: str, nome: str, logger=None) -> bool:
    """
    Porta l'istanza in mappa.
    Prima pulisce eventuali overlay con BACK rapidi, poi naviga.
    Garantisce uscita entro MAX_TENTATIVI_MAPPA tap (no loop infinito).
    """
    def log(msg):
        if logger: logger(nome, msg)

    # Leggi stato corrente
    s, _ = rileva(porta)
    log(f"Stato attuale: {s}")

    # Se c'è un overlay, pulisci prima
    if s not in ("home", "mappa"):
        s = _pulisci_overlay(porta, nome, logger)
        if s == "fallito":
            log("Impossibile raggiungere stato pulito - abbandono")
            return False

    if s == "mappa":
        log("Già in mappa")
        time.sleep(1.5)
        return True

    # Da home: fino a MAX_TENTATIVI_MAPPA tap con delay crescente
    # delay: 3s → 4s → 5s
    delays_post_tap = [3.0, 4.0, 5.0]

    for tentativo in range(MAX_TENTATIVI_MAPPA):
        delay = delays_post_tap[min(tentativo, len(delays_post_tap) - 1)]
        label = "primo" if tentativo == 0 else f"tentativo {tentativo + 1}"
        log(f"Tap mappa ({label}, attesa {delay:.0f}s)...")
        adb.tap(porta, (38, 505), delay_ms=0)
        time.sleep(delay)

        s_dopo, _ = rileva(porta)
        log(f"Stato dopo tap: {s_dopo}")

        if s_dopo == "mappa":
            time.sleep(1.5)
            return True

        if s_dopo not in ("home", "mappa"):
            # Overlay comparso dopo il tap → pulisci e riprova
            log(f"Overlay '{s_dopo}' dopo tap - pulisco")
            s_dopo = _pulisci_overlay(porta, nome, logger)
            if s_dopo == "fallito":
                log("Overlay persistente dopo tap - abbandono")
                return False
            if s_dopo == "mappa":
                time.sleep(1.5)
                return True
            # s_dopo == "home" → prossimo tentativo

        # Ancora in home → prossimo tentativo (con delay più lungo)
        if tentativo < MAX_TENTATIVI_MAPPA - 1:
            log(f"Ancora in home - riprovo (tentativo {tentativo + 2}/{MAX_TENTATIVI_MAPPA})")

    log(f"Impossibile raggiungere mappa dopo {MAX_TENTATIVI_MAPPA} tap - abbandono")
    return False

# ------------------------------------------------------------------------------
# Vai in home con verifica N conferme consecutive
# ------------------------------------------------------------------------------
def vai_in_home(porta: str, nome: str, logger=None, conferme: int = 3) -> bool:
    """
    Porta l'istanza in home.
    Prima pulisce eventuali overlay, poi verifica N letture consecutive di home.
    """
    def log(msg):
        if logger: logger(nome, msg)

    # Leggi stato corrente
    s, _ = rileva(porta)
    log(f"Stato attuale: {s}")

    # Overlay → pulisci
    if s not in ("home", "mappa"):
        s = _pulisci_overlay(porta, nome, logger)
        if s == "fallito":
            log("Impossibile uscire da overlay")
            return False

    # Se in mappa o home, usa BACK per tornare in home
    if s != "home":
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(2.0)

    # Verifica N conferme consecutive di home
    consecutive = 0
    for _ in range(conferme * 4):
        s, _ = rileva(porta)
        if s == "home":
            consecutive += 1
            if consecutive >= conferme:
                log(f"In home confermato ({conferme}x)")
                return True
            time.sleep(0.5)
        elif s in ("mappa",):
            consecutive = 0
            log(f"Stato {s} - BACK")
            adb.keyevent(porta, "KEYCODE_BACK")
            time.sleep(2.0)
        else:
            # Overlay ricomparso
            consecutive = 0
            log(f"Overlay '{s}' - pulisco")
            s = _pulisci_overlay(porta, nome, logger)
            if s == "fallito":
                log("Overlay persistente - abbandono")
                return False

    log("Impossibile confermare home")
    return False

# ------------------------------------------------------------------------------
# Conta squadre via OCR - con N letture per robustezza
# ------------------------------------------------------------------------------
def conta_squadre(porta: str, n_letture: int = 3) -> tuple:
    """
    Legge contatore squadre X/Y via OCR.
    Esegue n_letture tentativi e restituisce il valore più frequente.
    Se tutte falliscono ritorna (-1,-1,-1).
    """
    risultati = []

    for _ in range(n_letture):
        screen = adb.screenshot(porta)
        if not screen:
            continue
        crop = adb.crop_zona(screen, config.OCR_ZONA)
        if not crop:
            continue
        attive, totale = ocr.leggi_contatore(crop)
        if attive != -1:
            risultati.append((attive, totale))
        time.sleep(0.3)

    if not risultati:
        return (-1, -1, -1)

    from collections import Counter
    più_comune = Counter(risultati).most_common(1)[0][0]
    attive, totale = più_comune
    libere = max(0, totale - attive)
    return (attive, totale, libere)
