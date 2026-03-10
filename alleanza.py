# ==============================================================================
#  DOOMSDAY BOT V5 - alleanza.py
#  Raccolta ricompense dalla sezione Alleanza -> Dono
#
#  Flusso (dalla schermata home):
#    1. Tap pulsante Alleanza (menu in basso)
#    2. Tap icona Dono  → apre direttamente su "Ricompense del negozio"
#    3. Tab "Ricompense del negozio" → Tap "Rivendica" x10  (già attivo)
#    4. Tab "Ricompense attività"    → Tap "Raccogli tutto" (1 click)
#    5. Back x2 → torna in home
#
#  Risoluzione ADB: 960x540
# ==============================================================================

import time
import adb
import config


# ------------------------------------------------------------------------------
# Coordinate (risoluzione 960x540)
# ------------------------------------------------------------------------------
COORD_ALLEANZA       = (760, 505)   # Pulsante Alleanza nel menu in basso
COORD_DONO           = (877, 458)   # Icona Dono nel menu Alleanza
COORD_TAB_ATTIVITA   = (600,  75)   # Tab "Ricompense attività"
COORD_TAB_NEGOZIO    = (810,  75)   # Tab "Ricompense del negozio"
COORD_RACCOGLI_TUTTO = (856, 505)   # Pulsante "Raccogli tutto" (Attività)
COORD_RIVENDICA      = (856, 240)   # Pulsante "Rivendica" (Negozio, posizione fissa)

# Numero di click su Rivendica per le Ricompense Negozio
RIVENDICA_CLICK = 10


# ------------------------------------------------------------------------------
# Raccolta ricompense Alleanza
# ------------------------------------------------------------------------------
def raccolta_alleanza(porta: str, nome: str, logger=None) -> bool:
    """
    Raccoglie le ricompense dalla sezione Alleanza -> Dono.

    Args:
        porta:   porta ADB dell'istanza (es. "5555")
        nome:    nome istanza per il log (es. "FAU_00")
        logger:  callable(nome, msg) oppure None

    Returns:
        True se completato senza errori, False in caso di eccezione.
    """
    def log(msg):
        if logger: logger(nome, msg)

    try:
        log("Inizio raccolta ricompense Alleanza")

        # 1. Apri menu Alleanza
        log("Alleanza: tap pulsante Alleanza")
        adb.tap(porta, COORD_ALLEANZA)
        time.sleep(1.5)

        # 2. Apri sezione Dono (apre direttamente su Ricompense del negozio)
        log("Alleanza: tap Dono")
        adb.tap(porta, COORD_DONO)
        time.sleep(1.5)

        # 3. Ricompense Negozio → Rivendica x10 (tab già attivo all'apertura)
        log(f"Alleanza: Ricompense Negozio -> Rivendica x{RIVENDICA_CLICK}")
        adb.tap(porta, COORD_TAB_NEGOZIO)
        time.sleep(0.8)
        for i in range(RIVENDICA_CLICK):
            adb.tap(porta, COORD_RIVENDICA)
            time.sleep(0.5)

        # 4. Tab Ricompense Attività → Raccogli tutto
        log("Alleanza: tab Ricompense Attività -> Raccogli tutto")
        adb.tap(porta, COORD_TAB_ATTIVITA)
        time.sleep(0.8)
        adb.tap(porta, COORD_RACCOGLI_TUTTO)
        time.sleep(1.0)

        # 5. Back x3 → torna in home (extra back per stabilizzazione UI)
        log("Alleanza: chiusura (back x3)")
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(0.8)
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(1.5)
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(1.0)

        log("Raccolta ricompense Alleanza completata")
        return True

    except Exception as e:
        log(f"Errore raccolta Alleanza: {e}")
        # Tentativo di recupero con back x2
        try:
            adb.keyevent(porta, "KEYCODE_BACK")
            time.sleep(0.5)
            adb.keyevent(porta, "KEYCODE_BACK")
            time.sleep(0.5)
        except Exception:
            pass
        return False
