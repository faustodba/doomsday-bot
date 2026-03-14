# ==============================================================================
#  DOOMSDAY BOT V5 - config.py
#  Parametri globali di configurazione
# ==============================================================================

# --- Percorsi ---
#BOT_DIR        = r"E:\Bot-raccolta\V5"
BOT_DIR        = r"C:\Bot-raccolta\V5"
BS_EXE         = r"C:\Program Files\BlueStacks_nxt\HD-Player.exe"
BS_ADB         = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
BS_HIDE_WINDOW = False   # True = nasconde finestra HD-Player dopo avvio (richiede pywin32)
MUMU_ADB       = r"C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe"
ADB_EXE        = BS_ADB  # default BlueStacks, main.py lo sovrascrive a runtime
TESSERACT_EXE  = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
GAME_ACTIVITY  = "com.igg.android.doomsdaylastsurvivors/com.gpc.sdk.unity.GPCSDKMainActivity"

# --- Istanze ---
# [nome_finestra, nome_interno_BS, porta_adb, truppe_raccolta, max_squadre]
# truppe_raccolta: truppe per squadra (0 = MAX, None = usa TRUPPE_RACCOLTA globale)
# max_squadre    : numero massimo raccoglitori da inviare (1-5, 0 = usa tutte le libere)
ISTANZE = [
    ["FAU_00", "Pie64_13", "5685", 0, 5],
    ["FAU_01", "Pie64_6", "5615", 12000, 4],
    ["FAU_02", "Pie64",   "5555", 12000, 4],
    ["FAU_03", "Pie64_7", "5625", 12000, 4],
    ["FAU_04", "Pie64_8", "5635", 12000, 4],
    ["FAU_05", "Pie64_9", "5645", 12000, 4],
    ["FAU_06", "Pie64_11", "5665", 12000, 4],
    ["FAU_07", "Pie64_10", "5655", 12000, 4],
    ["FAU_08", "Pie64_12", "5675", 12000, 4],
    ["FAU_09", "Pie64_14", "5695", 10000, 3],
    
]

# --- Ciclo automatico ---
ISTANZE_BLOCCO         = 1    # istanze attive contemporaneamente
WAIT_MINUTI            = 1   # minuti di attesa tra un ciclo e l'altro

# --- Raccolta risorse ---
TRUPPE_RACCOLTA        = 12000  # truppe per squadra globale (0 = MAX)
MAX_TENTATIVI_RACCOLTA = 2      # tentativi massimi per singola squadra

# --- Coordinate tap (risoluzione 960x540) ---
TAP_LENTE           = (38,  325)
TAP_LENTE_COORD     = (380,  18)   # lente piccola barra superiore → popup coordinate
TAP_CAMPO           = (410, 450)
TAP_SEGHERIA        = (535, 450)
TAP_CERCA_CAMPO     = (410, 350)
TAP_CERCA_SEGHERIA  = (536, 351)
TAP_NODO            = (480, 280)
TAP_RACCOGLI        = (230, 390)
TAP_SQUADRA         = (700, 185)
TAP_MARCIA          = (727, 476)
TAP_TOGGLE_HOME_MAPPA = (38, 505)  # bottone in basso a sinistra: rifugio <-> mappa
TAP_CANCELLA        = (527, 469)
TAP_CAMPO_TESTO     = (748, 75)
TAP_OK_TASTIERA     = (879, 487)
TAP_LIVELLO_PIU     = (650, 286)
TAP_LIVELLO_MENO    = (430, 288)
LIVELLO_RACCOLTA    = 6

# --- Rilevamento stato ---
STATO_CHECK_X  = 40
STATO_CHECK_Y  = 505
STATO_SOGLIA_R = 160   # R<160=home, R>160=mappa, RGB<30=banner
# --- Rilevamento stato (robusto) ---
# Campiona più pixel attorno a STATO_CHECK_X/Y per ridurre falsi positivi dovuti a overlay/animazioni.
STATO_CHECK_OFFSETS = [
    (0, 0), (-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)
]
STATO_MIN_MAPPA_RGB_SUM = 20  # somma RGB minima per considerare la mappa (evita banner/schermo nero)

# --- Contatore squadre (OCR) ---
OCR_ZONA = (855, 115, 945, 145)   # zona crop screenshot per OCR X/4

# --- OCR ETA Marcia ---
# Zona con l'icona orologio + tempo percorrenza nella maschera "crea squadra"
# Calibrata su screenshot reali 960x540: testo "0:01:18" leggibile e verificato
OCR_MARCIA_ETA_ZONA       = (650, 440, 790, 465)
OCR_MARCIA_ETA_BASE_W     = 960
OCR_MARCIA_ETA_BASE_H     = 540
OCR_MARCIA_ETA_DEBUG_SAVE = False  # True = salva crop falliti in debug_eta/ per ri-calibrazione
OCR_MARCIA_ETA_MARGINE_S  = 5     # secondi extra attesa dopo ETA reale
OCR_MARCIA_ETA_MIN_S      = 8     # attesa minima anche se ETA è molto bassa

# --- Popup "Uscire dal gioco?" (rilevamento caricamento) ---
POPUP_CHECK_X   = 480
POPUP_CHECK_Y   = 270
POPUP_ANNULLA_X = 370
POPUP_ANNULLA_Y = 383
POPUP_OK_X      = 590
POPUP_OK_Y      = 367

# Range colore beige (pixel centrale popup)
BEIGE_R_MIN = 140;  BEIGE_R_MAX = 220
BEIGE_G_MIN = 130;  BEIGE_G_MAX = 210
BEIGE_B_MIN = 110;  BEIGE_B_MAX = 190

# Range colore giallo (pulsante OK popup)
POPUP_OK_R_MIN = 190;  POPUP_OK_R_MAX = 255
POPUP_OK_G_MIN = 130;  POPUP_OK_G_MAX = 200
POPUP_OK_B_MIN = 40;   POPUP_OK_B_MAX = 100

# --- Tempi ---
DELAY_AVVIO       = 5000    # ms pausa tra avvio istanze BS
TIMEOUT_BS        = 60      # secondi attesa finestra BS
TIMEOUT_ADB       = 120      # secondi attesa connessione ADB
TIMEOUT_CARICA    = 180     # secondi attesa caricamento gioco
DELAY_CARICA_INIZ = 45      # secondi attesa iniziale caricamento
DELAY_GIRO        = 2       # secondi pausa tra giri di polling
POLL_MS           = 1000    # ms intervallo polling
DELAY_CERCA       = 5000    # ms attesa dopo CERCA
DELAY_MARCIA      = 4000    # ms attesa dopo MARCIA

# --- Coordinate Messaggi (risoluzione 960x537) ---
MSG_ICONA_X         = 928
MSG_ICONA_Y         = 430
MSG_TAB_ALLEANZA_X  = 320
MSG_TAB_ALLEANZA_Y  = 28
MSG_TAB_SISTEMA_X   = 455
MSG_TAB_SISTEMA_Y   = 28
MSG_LEGGI_X         = 95
MSG_LEGGI_Y         = 510

# --- Schedulazione task periodici ---
# Intervallo minimo in ore tra due esecuzioni consecutive dello stesso task per istanza.
# Il task viene saltato se già eseguito entro l'intervallo, con log del tempo rimanente.
SCHEDULE_ORE_MESSAGGI  = 12   # raccolta ricompense messaggi
SCHEDULE_ORE_ALLEANZA  = 12   # raccolta ricompense alleanza

# --- Rifornimento alleanza ---
RIFORNIMENTO_ABILITATO     = True    # False = disabilita senza toccare il codice
RIFORNIMENTO_DESTINATARIO  = "FauMorfeus"
RIFORNIMENTO_AVATAR        = "templates/avatar_faumorfeus.png"
RIFORNIMENTO_BTN_TEMPLATE  = "templates/btn_risorse_approv.png"
RIFORNIMENTO_SOGLIA_M      = 5.0   # non invia se deposito < 10M per risorsa
RIFORNIMENTO_QTA_POMODORO  = 999_000_000
RIFORNIMENTO_QTA_LEGNO     = 999_000_000
RIFORNIMENTO_QTA_ACCIAIO   = 0
RIFORNIMENTO_QTA_PETROLIO  = 0

# --- MuMuPlayer ---
MUMU_MANAGER = r"C:\Program Files\Netease\MuMuPlayer\nx_main\MuMuManager.exe"

ISTANZE_MUMU = [
    ["FAU_02", "0", 16384],
    ["FAU_07", "1", 16416],
    ["FAU_03", "2", 16448],
    ["FAU_04", "3", 16480],
]
