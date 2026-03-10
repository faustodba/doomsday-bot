# ==============================================================================
#  DOOMSDAY BOT V5 - rifornimento.py  V5.3
#  Invio risorse al rifugio alleato (Risorse di Approvvigionamento)
#
#  Flusso:
#    1. Legge slot liberi raccoglitori (OCR contatore in home)
#    2. Controlla risorse mittente > soglia (10M default, considera tassa 24%)
#    3. Naviga: Alleanza → Membri → scorri R1/R2/R3/R4 → trova avatar
#    4. Tap membro → trova pulsante "Risorse di approvvigionamento" via template matching
#    5. Nella maschera: leggi residuo giornaliero e tempo percorrenza
#    6. Compila campi quantità → Tap VAI → torna in home
#    7. Rileggi slot liberi → ripeti finché slot==0 o risorse esaurite
#
#  Chiamato da raccolta.py PRIMA della raccolta risorse, quando si è in home.
# ==============================================================================

import time
import os
import cv2
import numpy as np
import adb
import ocr
import stato
import config
import log as _log

# ------------------------------------------------------------------------------
# Coordinate navigazione (risoluzione 960x540)
# ------------------------------------------------------------------------------
COORD_ALLEANZA_BTN  = (760, 505)   # pulsante Alleanza in home

COORD_MEMBRI        = (46, 188)    # tab Membri nel menu Alleanza

# Tab R1/R2/R3/R4 nella lista membri
COORD_TAB_R = {
    "R1": (175, 245),
    "R2": (305, 245),
    "R3": (435, 245),
    "R4": (565, 245),
}

# Swipe per scorrere lista membri (verso l'alto)
COORD_SWIPE_SU_START = (480, 420)
COORD_SWIPE_SU_END   = (480, 250)

# Maschera invio risorse — 4 campi quantità (coordinate fisse 960x540)
COORD_CAMPO = {
    "pomodoro": (620, 222),
    "legno":    (620, 272),
    "acciaio":  (620, 322),
    "petrolio": (620, 372),
}

COORD_VAI = (480, 448)   # pulsante VAI

# Zone OCR nella maschera invio risorse
OCR_RESIDUO_OGGI = (140, 225, 360, 255)   # "Provviste rimanenti di oggi: 20,000,000"
OCR_TEMPO        = (380, 410, 580, 440)   # "00:00:54"

# Area di ricerca avatar nella lista membri (zona lista, escluso header e sidebar)
AVATAR_ZONA      = (130, 155, 540, 490)

# Soglie template matching
AVATAR_SOGLIA        = 0.75
BTN_RISORSE_SOGLIA   = 0.75

# Max swipe per cercare avatar in ogni tab
MAX_SWIPE = 8

# Tassa invio default (24%) — preleva qta * (1 + tassa) dal mittente
TASSA_DEFAULT = 0.24

# Quantità default per singolo invio (unità assolute)
QTA_DEFAULT = {
    "pomodoro": 500_000,
    "legno":    500_000,
    "acciaio":  0,
    "petrolio": 0,
}

# Soglia minima risorse mittente per inviare (milioni)
SOGLIA_MIN_M = 10.0

# ------------------------------------------------------------------------------
# Leggi slot liberi raccoglitori da home
# ------------------------------------------------------------------------------
def _slot_liberi(porta: str) -> int:
    """Legge contatore raccoglitori in home. Ritorna slot liberi (0-4)."""
    attive, totale, libere = stato.conta_squadre(porta, n_letture=3)
    if attive == -1 or totale == -1:
        return 4  # fallback ottimistico
    return libere

# ------------------------------------------------------------------------------
# Template matching generico
# ------------------------------------------------------------------------------
def _trova_template(screen_path: str, template_path: str, zona=None, soglia=0.75):
    """
    Cerca template in screen (opzionalmente in zona=(x1,y1,x2,y2)).
    Ritorna (cx, cy) coordinate assolute, oppure None.
    """
    if not screen_path or not os.path.exists(screen_path):
        return None
    if not template_path or not os.path.exists(template_path):
        return None

    img  = cv2.imread(screen_path)
    tmpl = cv2.imread(template_path)
    if img is None or tmpl is None:
        return None

    offset_x, offset_y = 0, 0
    if zona:
        x1, y1, x2, y2 = zona
        img = img[y1:y2, x1:x2]
        offset_x, offset_y = x1, y1

    result = cv2.matchTemplate(img, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val < soglia:
        return None

    th, tw = tmpl.shape[:2]
    cx = max_loc[0] + tw // 2 + offset_x
    cy = max_loc[1] + th // 2 + offset_y
    return (cx, cy)

# ------------------------------------------------------------------------------
# Cerca avatar destinatario nella lista visibile
# ------------------------------------------------------------------------------
def _cerca_avatar_visibile(porta: str, template_path: str, logger=None, nome: str = ""):
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    screen = adb.screenshot(porta)
    if not screen:
        return None

    coord = _trova_template(screen, template_path, zona=AVATAR_ZONA, soglia=AVATAR_SOGLIA)
    if not coord:
        return None

    cx, cy = coord
    tap_x = 290 if cx < 490 else 680
    log(f"Avatar trovato a ({cx},{cy}) → tap ({tap_x},{cy})")
    return (tap_x, cy)

# ------------------------------------------------------------------------------
# Cerca pulsante "Risorse di approvvigionamento" via template matching
# Posizione variabile — NON usare coordinate fisse
# ------------------------------------------------------------------------------
def _trova_pulsante_risorse(porta: str, logger=None, nome: str = ""):
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    template_path = getattr(config, "RIFORNIMENTO_BTN_TEMPLATE",
                            "templates/btn_risorse_approv.png")

    screen = adb.screenshot(porta)
    if not screen:
        return None

    coord = _trova_template(screen, template_path, soglia=BTN_RISORSE_SOGLIA)
    if coord:
        log(f"Pulsante Risorse trovato a {coord}")
        return coord

    log("Pulsante Risorse non trovato via template matching")
    return None

# ------------------------------------------------------------------------------
# Leggi residuo giornaliero dalla maschera invio
# ------------------------------------------------------------------------------
def _leggi_residuo(porta: str) -> float:
    """Ritorna residuo in milioni, -1 se OCR fallisce, 0 se esaurito."""
    screen = adb.screenshot(porta)
    if not screen:
        return -1
    valore = ocr.leggi_numero_zona(screen, OCR_RESIDUO_OGGI)
    if valore is None or valore < 0:
        return -1
    return valore / 1_000_000

# ------------------------------------------------------------------------------
# Leggi tempo di percorrenza dalla maschera invio
# ------------------------------------------------------------------------------
def _leggi_tempo_percorrenza(porta: str) -> int:
    """Ritorna secondi totali del tempo percorrenza, 0 se OCR fallisce."""
    screen = adb.screenshot(porta)
    if not screen:
        return 0
    testo = ocr.leggi_testo_zona(screen, OCR_TEMPO).strip()
    parti = testo.replace(".", ":").split(":")
    try:
        if len(parti) == 3:
            return int(parti[0]) * 3600 + int(parti[1]) * 60 + int(parti[2])
        elif len(parti) == 2:
            return int(parti[0]) * 60 + int(parti[1])
    except (ValueError, IndexError):
        pass
    return 0

# ------------------------------------------------------------------------------
# Naviga alla maschera "Risorse di Approvvigionamento"
# Scorre R1→R2→R3→R4 con swipe fino a trovare l'avatar
# ------------------------------------------------------------------------------
def _naviga_a_maschera(porta: str, logger=None, nome: str = "") -> bool:
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    template_avatar = getattr(config, "RIFORNIMENTO_AVATAR", "")
    if not template_avatar or not os.path.exists(template_avatar):
        log(f"ERRORE: template avatar non trovato: {template_avatar}")
        return False

    # 1. Apri Alleanza
    log("Tap Alleanza")
    adb.tap(porta, COORD_ALLEANZA_BTN, delay_ms=1500)

    # 2. Tap Membri
    log("Tap Membri")
    adb.tap(porta, COORD_MEMBRI, delay_ms=1500)

    # 3. Scorri R1→R2→R3→R4 cercando avatar
    coord_tap = None
    for tab_nome, tab_coord in COORD_TAB_R.items():
        log(f"Cerco avatar nel tab {tab_nome}")
        adb.tap(porta, tab_coord, delay_ms=1500)

        for swipe_n in range(MAX_SWIPE + 1):
            coord_tap = _cerca_avatar_visibile(porta, template_avatar, logger, nome)
            if coord_tap:
                log(f"Avatar trovato in {tab_nome} dopo {swipe_n} swipe")
                break
            if swipe_n < MAX_SWIPE:
                log(f"{tab_nome}: swipe {swipe_n + 1}/{MAX_SWIPE}")
                adb.scroll(porta,
                           COORD_SWIPE_SU_START[0], COORD_SWIPE_SU_START[1],
                           COORD_SWIPE_SU_END[1], durata_ms=600)
                time.sleep(1.5)

        if coord_tap:
            break

    if not coord_tap:
        log("ERRORE: avatar non trovato in R1-R4")
        return False

    # 4. Tap membro → popup 4 pulsanti (Chat | Info | Rinforzo | Risorse)
    log(f"Tap membro a {coord_tap}")
    adb.tap(porta, coord_tap, delay_ms=1500)

    # 5. Trova pulsante "Risorse di approvvigionamento" via template matching
    btn_coord = None
    for tentativo in range(3):
        btn_coord = _trova_pulsante_risorse(porta, logger, nome)
        if btn_coord:
            break
        time.sleep(0.8)

    if not btn_coord:
        log("ERRORE: pulsante Risorse non trovato - chiudo popup con BACK")
        adb.keyevent(porta, "KEYCODE_BACK")
        return False

    # 6. Tap "Risorse di approvvigionamento"
    log(f"Tap Risorse di approvvigionamento a {btn_coord}")
    adb.tap(porta, btn_coord, delay_ms=2000)
    return True

# ------------------------------------------------------------------------------
# Compila campi e preme VAI nella maschera invio
# ------------------------------------------------------------------------------
def _compila_e_invia(porta: str, quantita: dict, logger=None, nome: str = ""):
    """
    Ritorna (ok: bool, tempo_percorrenza: int).
    ok=False se residuo giornaliero esaurito o errore.
    """
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    # Leggi residuo giornaliero — se 0 non inviare
    residuo_m = _leggi_residuo(porta)
    if residuo_m >= 0:
        log(f"Residuo giornaliero: {residuo_m:.1f}M")
    else:
        log("Residuo giornaliero: OCR fallito - procedo")

    if residuo_m == 0:
        log("Residuo giornaliero esaurito - stop")
        return False, 0

    # Leggi tempo percorrenza
    tempo = _leggi_tempo_percorrenza(porta)
    log(f"Tempo percorrenza: {tempo}s")

    # Compila campi quantità
    for risorsa, qta in quantita.items():
        if qta <= 0:
            continue
        coord = COORD_CAMPO.get(risorsa)
        if not coord:
            continue
        log(f"Compila {risorsa}: {qta:,}")
        adb.tap(porta, coord, delay_ms=600)
        adb.keyevent(porta, "KEYCODE_CTRL_A")
        time.sleep(0.2)
        adb.keyevent(porta, "KEYCODE_DEL")
        time.sleep(0.2)
        adb.input_text(porta, str(qta))
        time.sleep(0.4)
        adb.tap(porta, config.TAP_OK_TASTIERA, delay_ms=500)

    # Tap VAI
    log("Tap VAI")
    adb.tap(porta, COORD_VAI, delay_ms=2000)
    return True, tempo

# ------------------------------------------------------------------------------
# Funzione principale
# ------------------------------------------------------------------------------
def esegui_rifornimento(porta: str, nome: str,
                        pomodoro_m: float = -1, legno_m: float = -1,
                        acciaio_m: float = -1, petrolio_m: float = -1,
                        logger=None, ciclo: int = 0) -> int:
    """
    Esegue rifornimento risorse al rifugio alleato configurato.
    Ritorna numero di spedizioni effettuate.
    """
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    nome_rifugio = getattr(config, "RIFORNIMENTO_DESTINATARIO", "")
    soglia       = getattr(config, "RIFORNIMENTO_SOGLIA_M", SOGLIA_MIN_M)
    tassa        = getattr(config, "RIFORNIMENTO_TASSA", TASSA_DEFAULT)

    if not nome_rifugio:
        log("RIFORNIMENTO_DESTINATARIO non configurato - skip")
        return 0

    # Quantità per spedizione da config (con fallback a default)
    quantita = {
        "pomodoro": getattr(config, "RIFORNIMENTO_QTA_POMODORO", QTA_DEFAULT["pomodoro"]),
        "legno":    getattr(config, "RIFORNIMENTO_QTA_LEGNO",    QTA_DEFAULT["legno"]),
        "acciaio":  getattr(config, "RIFORNIMENTO_QTA_ACCIAIO",  QTA_DEFAULT["acciaio"]),
        "petrolio": getattr(config, "RIFORNIMENTO_QTA_PETROLIO", QTA_DEFAULT["petrolio"]),
    }

    # Risorse mittente correnti (aggiornate dopo ogni spedizione)
    risorse_m = {
        "pomodoro": pomodoro_m,
        "legno":    legno_m,
        "acciaio":  acciaio_m,
        "petrolio": petrolio_m,
    }

    def _ha_risorse(risorsa: str) -> bool:
        """True se mittente ha abbastanza risorse (considera tassa)."""
        rm = risorse_m.get(risorsa, -1)
        if rm < 0:
            return True  # valore non noto → non bloccare
        qta = quantita.get(risorsa, 0)
        necessario_m = (qta * (1 + tassa)) / 1_000_000
        return rm >= max(soglia, necessario_m)

    def _risorse_attive() -> dict:
        return {r: q for r, q in quantita.items()
                if q > 0 and _ha_risorse(r)}

    risorse_da_inviare = _risorse_attive()
    if not risorse_da_inviare:
        log(f"Nessuna risorsa disponibile sopra soglia ({soglia}M) - skip")
        return 0

    log(f"Risorse configurate: {list(risorse_da_inviare.keys())} | soglia: {soglia}M | tassa: {tassa*100:.0f}%")

    spedizioni   = 0
    tempo_attesa = 0

    while True:
        # Rileggi slot liberi dalla home
        slot = _slot_liberi(porta)
        log(f"Slot liberi: {slot}")

        if slot == 0:
            if tempo_attesa > 0:
                log(f"Slot occupati - attendo {tempo_attesa + 5}s (tempo percorrenza + margine)")
                time.sleep(tempo_attesa + 5)
                slot = _slot_liberi(porta)
                log(f"Slot dopo attesa: {slot}")
            if slot == 0:
                log("Nessun slot libero - stop rifornimento")
                break

        # Ricalcola risorse attive ad ogni iterazione
        risorse_da_inviare = _risorse_attive()
        if not risorse_da_inviare:
            log("Risorse mittente sotto soglia - stop rifornimento")
            break

        # Naviga alla maschera (deve rifare la navigazione ad ogni spedizione
        # perché il gioco esce dalla maschera dopo ogni VAI)
        if not _naviga_a_maschera(porta, logger, nome):
            log("Navigazione fallita - interruzione rifornimento")
            for _ in range(5):
                adb.keyevent(porta, "KEYCODE_BACK")
                time.sleep(0.5)
            stato.vai_in_home(porta, nome, logger)
            break

        # Compila e invia
        ok, tempo = _compila_e_invia(porta, risorse_da_inviare, logger, nome)
        if not ok:
            log("Invio fallito o residuo esaurito - stop rifornimento")
            adb.keyevent(porta, "KEYCODE_BACK")
            time.sleep(0.5)
            stato.vai_in_home(porta, nome, logger)
            break

        if tempo > 0:
            tempo_attesa = tempo

        spedizioni += 1
        log(f"Spedizione {spedizioni} completata (tempo: {tempo}s)")
        _log.registra_evento(ciclo, nome, "rifornimento_ok", spedizioni, 1,
                             f"risorse={list(risorse_da_inviare.keys())}")

        # Aggiorna stima risorse mittente (sottrai prelevato con tassa)
        for risorsa in risorse_da_inviare:
            qta = risorse_da_inviare[risorsa]
            prelevato_m = (qta * (1 + tassa)) / 1_000_000
            if risorse_m.get(risorsa, -1) >= 0:
                risorse_m[risorsa] -= prelevato_m

        # Pausa stabilizzazione prima di rileggere lo stato
        time.sleep(3.0)

    log(f"Rifornimento completato: {spedizioni} spedizioni totali")
    return spedizioni
