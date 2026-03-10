# ==============================================================================
#  DOOMSDAY BOT V5 - rifornimento.py
#  Invio risorse al rifugio alleato (Risorse di Approvvigionamento)
#
#  Flusso:
#    1. Legge contatore slot liberi (OCR in home)
#    2. Controlla risorse disponibili (pomodoro/legno > soglia)
#    3. Naviga: Alleanza → Membri → R3 → scroll + OCR nome → tap membro
#    4. Tap "Risorse di approvvigionamento"
#    5. Per ogni risorsa disponibile e slot libero:
#       - Tap campo quantità → digita 999999999 → OK → VAI
#    6. Torna in home
#
#  Chiamato da raccolta.py PRIMA della raccolta risorse, quando si è in home.
# ==============================================================================

import time
import adb
import ocr
import stato
import config

# ------------------------------------------------------------------------------
# Coordinate navigazione (risoluzione 960x540)
# ------------------------------------------------------------------------------
COORD_ALLEANZA_BTN   = (760, 505)   # pulsante Alleanza in home (già in alleanza.py)
COORD_MEMBRI         = (46, 188)    # tab Membri nel menu Alleanza
COORD_R3             = (480, 245)   # tab R3 nella lista membri
COORD_SWIPE_START    = (480, 420)   # swipe verso l'alto per scorrere lista
COORD_SWIPE_END      = (480, 280)   # fine swipe

# Popup membro (compare dopo tap sul membro)
COORD_RISORSE_APPROV = (442, 320)   # pulsante "Risorse di approvvigionamento"

# Maschera invio risorse
COORD_CAMPO_POMODORO = (730, 222)   # campo quantità pomodoro
COORD_CAMPO_LEGNO    = (730, 272)   # campo quantità legno
COORD_VAI            = (480, 430)   # pulsante VAI

# OCR zona nome membro nella lista (colonna sinistra e destra)
# La lista ha 2 colonne, ogni riga è alta ~70px
# Prima riga visibile parte da y~280, nomi a x~220 (sx) e x~700 (dx)
OCR_LISTA_RIGHE = [
    # (x1, y1, x2, y2, colonna)  — coordinate crop per OCR nome
    (140, 270, 440, 310, "sx"),
    (530, 270, 830, 310, "dx"),
    (140, 340, 440, 380, "sx"),
    (530, 340, 830, 380, "dx"),
    (140, 410, 440, 450, "sx"),
    (530, 410, 830, 450, "dx"),
]

# Coordinate tap centro cella (per selezionare il membro trovato)
OCR_LISTA_TAP = [
    (290, 290, "sx"),
    (680, 290, "dx"),
    (290, 360, "sx"),
    (680, 360, "dx"),
    (290, 430, "sx"),
    (680, 430, "dx"),
]

# Quantità da digitare (il gioco la converte al massimo consentito)
QUANTITA_MAX = "999999999"

# Soglia minima risorse per inviare (in unità assolute)
SOGLIA_MIN_M = 10.0   # 10M

# Max swipe per cercare il membro nella lista
MAX_SWIPE = 6

# ------------------------------------------------------------------------------
# Leggi slot liberi raccoglitori (OCR contatore X/Y in home)
# ------------------------------------------------------------------------------
def _slot_liberi(porta: str) -> int:
    """Legge il contatore raccoglitori e ritorna gli slot liberi."""
    screen = adb.screenshot(porta)
    if not screen:
        return 4  # fallback: assume tutti liberi
    crop = adb.crop_zona(screen, config.OCR_ZONA)
    if not crop:
        return 4
    attive, totale = ocr.leggi_contatore(crop)
    if attive == -1 or totale == -1:
        return 4  # OCR fallito: assume tutti liberi
    return max(0, totale - attive)

# ------------------------------------------------------------------------------
# Cerca l'avatar del membro nella lista via template matching OpenCV
# Ritorna (x, y) del tap sul membro, o None se non trovato
# ------------------------------------------------------------------------------
def _cerca_avatar_visibile(porta: str, template_path: str) -> tuple:
    """
    Scatta screenshot e cerca l'avatar via template matching OpenCV.
    Ritorna le coordinate (x,y) del tap sul membro, o None se non trovato.
    """
    import cv2
    import numpy as np

    screen = adb.screenshot(porta)
    if not screen:
        return None

    img = cv2.imread(screen)
    tmpl = cv2.imread(template_path)
    if img is None or tmpl is None:
        return None

    # Cerca nella zona lista (y: 160-480, x: 130-850)
    zona = img[160:480, 130:850]
    result = cv2.matchTemplate(zona, tmpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)


    if max_val < 0.75:
        return None

    # Centro avatar nella zona + offset crop
    th, tw = tmpl.shape[:2]
    cx = max_loc[0] + tw // 2 + 130
    cy = max_loc[1] + th // 2 + 160

    # Tap al centro della cella (colonna sx o dx)
    tap_x = 290 if cx < 490 else 680
    tap_y = cy
    return (tap_x, tap_y)


# ------------------------------------------------------------------------------
# Cerca il pulsante "Risorse di approvvigionamento" nel popup via OCR
# Il popup compare in posizione variabile a seconda dello scroll della lista
# ------------------------------------------------------------------------------
def _trova_pulsante_risorse(porta: str) -> tuple:
    """Cerca il pulsante Risorse di approvvigionamento nel popup via OCR."""
    screen = adb.screenshot(porta)
    if not screen:
        return None

    # Scansiona area centrale popup (y: 150-450) a step di 40px
    step = 40
    for y1 in range(150, 430, step):
        y2 = y1 + step
        crop = adb.crop_zona(screen, (130, y1, 530, y2))
        if not crop:
            continue
        testo = ocr.leggi_testo(crop).lower()
        if "risorse" in testo or "approvv" in testo:
            return (330, y1 + step // 2)
    return None

# ------------------------------------------------------------------------------
# Naviga alla maschera Risorse di Approvvigionamento
# Ritorna True se la maschera è aperta, False se fallisce
# ------------------------------------------------------------------------------
def _naviga_a_maschera(porta: str, nome_rifugio: str, logger=None, nome: str = "") -> bool:
    """
    Navigazione completa: Alleanza → Membri → R3 → scroll → tap membro → tap Risorse.
    """
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    # 1. Apri menu Alleanza
    log("Tap Alleanza")
    adb.tap(porta, COORD_ALLEANZA_BTN, delay_ms=2000)

    # 2. Tap Membri
    log("Tap Membri")
    adb.tap(porta, COORD_MEMBRI, delay_ms=2000)

    # 3. Assicurati che tutti i tab siano chiusi — tap R3 per aprirlo
    #    Se R1 o altri erano aperti, chiudiamoli con BACK e riaprendo
    log("Tap R3")
    adb.tap(porta, COORD_R3, delay_ms=2000)

    # 4. Cerca avatar nella lista con scroll
    template_path = getattr(config, "RIFORNIMENTO_AVATAR", "")
    log(f"Ricerca avatar '{nome_rifugio}' nella lista R3...")
    coord_tap = None

    for swipe_n in range(MAX_SWIPE + 1):
        coord_tap = _cerca_avatar_visibile(porta, template_path)
        if coord_tap:
            log(f"Avatar trovato dopo {swipe_n} swipe")
            break
        if swipe_n < MAX_SWIPE:
            log(f"Non trovato - swipe {swipe_n + 1}/{MAX_SWIPE}")
            adb.scroll(porta, COORD_SWIPE_START[0], COORD_SWIPE_START[1], COORD_SWIPE_END[1], durata_ms=600)
            time.sleep(5.0)

    if not coord_tap:
        log(f"ERRORE: avatar '{nome_rifugio}' non trovato dopo {MAX_SWIPE} swipe")
        return False

    # 5. Tap sul membro → compare popup
    log(f"Tap membro a {coord_tap}")
    adb.tap(porta, coord_tap, delay_ms=1500)

    # 6. Cerca e tap "Risorse di approvvigionamento" via OCR
    log("Ricerca pulsante Risorse di approvvigionamento...")
    coord_risorse = None
    for _ in range(3):
        coord_risorse = _trova_pulsante_risorse(porta)
        if coord_risorse:
            break
        time.sleep(0.5)

    if not coord_risorse:
        log("ERRORE: pulsante Risorse non trovato - uso coordinate fisse")
        coord_risorse = COORD_RISORSE_APPROV

    log(f"Tap Risorse di approvvigionamento a {coord_risorse}")
    adb.tap(porta, coord_risorse, delay_ms=2000)

    return True

# ------------------------------------------------------------------------------
# Invia una risorsa (pomodoro o legno)
# Ritorna True se VAI premuto con successo
# ------------------------------------------------------------------------------
def _invia_risorsa(porta: str, tipo: str, logger=None, nome: str = "") -> bool:
    """
    Compila il campo della risorsa e preme VAI.
    tipo: 'pomodoro' | 'legno'
    """
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    coord_campo = COORD_CAMPO_POMODORO if tipo == "pomodoro" else COORD_CAMPO_LEGNO

    # Tap sul campo quantità
    log(f"Tap campo {tipo}")
    adb.tap(porta, coord_campo, delay_ms=800)

    # Digita quantità massima
    log(f"Digita {QUANTITA_MAX}")
    adb.input_text(porta, QUANTITA_MAX)
    time.sleep(0.5)

    # Conferma tastiera (OK)
    adb.tap(porta, (config.TAP_OK_TASTIERA[0], config.TAP_OK_TASTIERA[1]), delay_ms=800)

    # Tap VAI
    log("Tap VAI")
    adb.tap(porta, COORD_VAI, delay_ms=3000)

    return True

# ------------------------------------------------------------------------------
# Funzione principale
# ------------------------------------------------------------------------------
def esegui_rifornimento(porta: str, nome: str, pomodoro_m: float, legno_m: float,
                         logger=None) -> int:
    """
    Esegue il rifornimento risorse al rifugio alleato configurato.

    porta       : porta ADB istanza
    nome        : nome istanza (per log)
    pomodoro_m  : pomodoro disponibile in milioni (da OCR raccolta precedente, -1 se non noto)
    legno_m     : legno disponibile in milioni
    logger      : funzione log(nome, msg)

    Ritorna il numero di spedizioni effettuate (0 se nessuna).
    """
    def log(msg):
        if logger: logger(nome, f"[RIF] {msg}")

    nome_rifugio = getattr(config, "RIFORNIMENTO_DESTINATARIO", "")
    soglia       = getattr(config, "RIFORNIMENTO_SOGLIA_M", SOGLIA_MIN_M)

    if not nome_rifugio:
        log("RIFORNIMENTO_DESTINATARIO non configurato - skip")
        return 0

    # 1. Controlla slot liberi
    slot = _slot_liberi(porta)
    log(f"Slot raccoglitori liberi: {slot}")
    if slot == 0:
        log("Nessun slot libero - skip rifornimento")
        return 0

    # 2. Determina risorse da inviare
    risorse_da_inviare = []
    if pomodoro_m < 0 or pomodoro_m > soglia:
        risorse_da_inviare.append("pomodoro")
    if legno_m < 0 or legno_m > soglia:
        risorse_da_inviare.append("legno")

    if not risorse_da_inviare:
        log(f"Risorse sotto soglia ({soglia}M) - skip rifornimento")
        return 0

    # Limita alle risorse disponibili per gli slot liberi
    risorse_da_inviare = risorse_da_inviare[:slot]
    log(f"Risorse da inviare: {risorse_da_inviare} (slot: {slot})")

    spedizioni = 0

    for i, risorsa in enumerate(risorse_da_inviare):
        log(f"Spedizione {i+1}/{len(risorse_da_inviare)}: {risorsa}")

        # Naviga alla maschera (ogni volta — il gioco chiude il popup dopo VAI)
        if not _naviga_a_maschera(porta, nome_rifugio, logger, nome):
            log("Navigazione fallita - interruzione rifornimento")
            # Torna in home con BACK
            for _ in range(4):
                adb.keyevent(porta, "KEYCODE_BACK")
                time.sleep(0.5)
            return spedizioni

        # Invia risorsa
        if _invia_risorsa(porta, risorsa, logger, nome):
            spedizioni += 1
            log(f"Spedizione {risorsa} completata")
        else:
            log(f"Spedizione {risorsa} fallita")

        # Dopo VAI siamo tornati in home — pausa stabilizzazione
        time.sleep(3.0)

    log(f"Rifornimento completato: {spedizioni} spedizioni")
    return spedizioni
