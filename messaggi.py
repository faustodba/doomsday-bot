# ==============================================================================
#  DOOMSDAY BOT V5 - messaggi.py
#  Raccolta ricompense dalla sezione Messaggi (tab Alleanza + Sistema)
#
#  Sequenza per ogni istanza (prima della raccolta risorse):
#    1. Tap icona busta messaggi (home)
#    2. Tap tab ALLEANZA → Leggi e richiedi tutto
#    3. Tap tab SISTEMA  → Leggi e richiedi tutto
#    4. BACK
# ==============================================================================

import time
import adb
import config


def raccolta_messaggi(porta: str, nome: str, logger=None) -> bool:
    """
    Raccoglie le ricompense dalla sezione Messaggi.

    Args:
        porta:   porta ADB dell'istanza (es. "5555")
        nome:    nome istanza per il log (es. "FAU_02")
        logger:  callable(nome, msg) oppure None

    Returns:
        True se completato senza errori, False in caso di eccezione.
    """
    def log(msg):
        if logger: logger(nome, msg)

    try:
        log("Inizio raccolta messaggi")

        # 1. Apri schermata messaggi
        adb.tap(porta, (config.MSG_ICONA_X, config.MSG_ICONA_Y))
        time.sleep(1.5)

        # 2. Tab ALLEANZA → raccogli
        log("Messaggi: tab ALLEANZA -> Leggi e richiedi tutto")
        adb.tap(porta, (config.MSG_TAB_ALLEANZA_X, config.MSG_TAB_ALLEANZA_Y))
        time.sleep(1.0)
        adb.tap(porta, (config.MSG_LEGGI_X, config.MSG_LEGGI_Y))
        time.sleep(1.5)

        # 3. Tab SISTEMA → raccogli
        log("Messaggi: tab SISTEMA -> Leggi e richiedi tutto")
        adb.tap(porta, (config.MSG_TAB_SISTEMA_X, config.MSG_TAB_SISTEMA_Y))
        time.sleep(1.0)
        adb.tap(porta, (config.MSG_LEGGI_X, config.MSG_LEGGI_Y))
        time.sleep(1.5)

        # 4. Chiudi con BACK
        adb.keyevent(porta, "KEYCODE_BACK")
        time.sleep(1.0)

        log("Raccolta messaggi completata")
        return True

    except Exception as e:
        log(f"Errore raccolta messaggi: {e}")
        return False
