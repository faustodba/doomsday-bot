# 🤖 Doomsday Bot V5

Bot Python per l'automazione della raccolta risorse nel gioco **Doomsday: Last Survivors** su emulatori Android.

---

## 📋 Descrizione

Il bot gestisce in modo automatico le operazioni ripetitive del gioco su più istanze in parallelo:

- Raccolta messaggi (tab Alleanza e Sistema)
- Raccolta ricompense Alleanza (Negozio + Attività)
- Invio rifornimenti ad altri giocatori
- Ricerca e invio raccoglitori su nodi risorse (campo/segheria)
- Bilanciamento automatico delle risorse (pomodoro vs legno)
- Gestione blacklist nodi per evitare sovrapposizioni tra raccoglitori

---

## 🖥️ Emulatori supportati

| Emulatore | Versione | Note |
|-----------|----------|------|
| BlueStacks | 5+ | Avviato e stoppato per ogni ciclo |
| MuMuPlayer | 12 | Integrato con Provider Pattern |

---

## ⚙️ Architettura

```
main.py
│
├── Pool con Semaphore (max N istanze parallele)
│   └── worker per istanza
│       ├── avvia_blocco()         → emulatore (BS/MuMu)
│       ├── attendi_e_raccogli_istanza() → emulatore_base
│       │   ├── polling popup (3 conferme)
│       │   └── raccolta_istanza() → raccolta.py
│       │       ├── messaggi.py
│       │       ├── alleanza.py
│       │       ├── rifornimento.py
│       │       └── loop invio squadre
│       └── chiudi_istanza()
└── cleanup_istanze_appese()
```

### Istanze configurate

| Istanza | Emulatore | Porta ADB |
|---------|-----------|-----------|
| FAU_00 | BlueStacks | configurabile |
| FAU_01 | BlueStacks | 5615 |
| FAU_02 | BlueStacks | 5555 |
| FAU_03–08 | BlueStacks/MuMu | configurabili |

---

## 📦 Moduli

| Modulo | Descrizione |
|--------|-------------|
| `main.py` | Entry point, pool con semaforo, loop principale |
| `raccolta.py` | Flusso raccolta risorse per singola istanza |
| `alleanza.py` | Automazione menu Alleanza/Dono |
| `messaggi.py` | Raccolta messaggi in-game |
| `rifornimento.py` | Invio rifornimenti ad altri giocatori |
| `bluestacks.py` | Gestione ciclo vita BlueStacks |
| `mumu.py` | Gestione ciclo vita MuMuPlayer 12 |
| `emulatore_base.py` | Logica comune condivisa tra emulatori |
| `adb.py` | Comandi ADB (tap, screenshot, keyevent) |
| `ocr.py` | Lettura testo da screenshot (Tesseract) |
| `stato.py` | Rilevamento stato gioco (home/mappa) |
| `config.py` | Configurazione centralizzata |
| `timing.py` | EWMA adaptive timing |
| `log.py` | Logging centralizzato |
| `debug.py` | Salvataggio screenshot diagnostici |
| `status.py` | Scrittura `status.json` per dashboard |
| `report.py` | Generazione report HTML a fine ciclo |
| `launcher.py` | GUI tkinter per avvio istanze |

---

## 🔧 Requisiti

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [ADB (Android Debug Bridge)](https://developer.android.com/tools/adb)
- BlueStacks 5+ e/o MuMuPlayer 12
- Librerie Python:

```bash
pip install pillow pytesseract opencv-python
```

---

## 🚀 Avvio

```bash
cd C:\Bot-raccolta\V5

# Avvio interattivo (chiede emulatore e istanze)
python main.py

# Avvio diretto BlueStacks
python main.py --emulatore 1

# Avvio diretto MuMuPlayer
python main.py --emulatore 2

# Istanze specifiche
python main.py --emulatore 1 --istanze FAU_01,FAU_02
```

---

## 📊 Flusso raccolta per istanza

```
messaggi → alleanza → rifornimento → vai_in_mappa → loop invio squadre
```

### Loop invio squadre

```
lettura contatore reale
  └── per ogni squadra da inviare:
        CERCA → OCR coordinate nodo
        ├── nodo in blacklist? → attendi / skip tipo
        └── nodo libero → TAP_NODO → prenota blacklist
              → RACCOGLI → SQUADRA → MARCIA
              → rileggi contatore reale
              ├── aumentato → squadra confermata ✅
              └── invariato → squadra respinta → rilascia blacklist 🔄
```

### Blacklist nodi
- **V5.12**: blacklist transazionale con stati **RESERVED/COMMITTED** (TTL 120s su COMMITTED).

- TTL fisso: **120 secondi**
- Se nodo in blacklist → riprova CERCA (lente+tipo+cerca)
- Se stesso nodo ancora → attesa 120s → riprova
- Se ancora stesso nodo → skip tipo corrente
- Blacklist rilasciata se errore prima del tap MARCIA

---

## ⏱️ Timing adattivo

Il bot usa **EWMA (Exponentially Weighted Moving Average)** per stimare il tempo di caricamento di ogni istanza:

- Alpha: `0.3`
- Outlier detection: z-score
- Attesa minima: `30 secondi`
- La stima viene aggiornata ad ogni ciclo per ogni istanza

---

## 📁 Struttura file di output

```
C:\Bot-raccolta\V5\
├── bot.log              # log principale
├── status.json          # stato real-time per dashboard
├── timing.json          # storico tempi di caricamento
└── debug\
    └── ciclo_NNN\
        ├── report_ciclo_NNN.html
        └── *.png        # screenshot diagnostici
```

---

## 🗂️ Contesto sessioni Claude

Questo repository include un file `CONTEXT.md` usato per mantenere il contesto
tra sessioni di sviluppo con Claude AI.

---

## 📜 Storico versioni

| Versione | Note |
|----------|------|
| V2 | AutoHotkey — 14 istanze Sandboxie |
| V3 | Migrazione Python, singolo emulatore |
| V4 | Multithreading, multi-emulatore, MuMu integration |
| V5 | Alleanza, messaggi, rifornimento, launcher, dashboard |
| V5.5 | Screenshot prima del tap nodo |
| V5.6 | raccolta.py refactor |
| V5.7 | rifornimento integrato nel flusso principale |
| V5.8 | Fix blacklist TTL, fix report TypeError, fix cleanup PID |
| V5.9 | Lettura reale post-MARCIA, blacklist rilasciata su errore, max 3 fallimenti consecutivi |

V5.12 \
Blacklist transazionale: reserve/commit/rollback (TTL COMMITTED 120s) \
