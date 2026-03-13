# 🤖 Doomsday Bot V5

Bot Python per l'automazione della raccolta risorse nel gioco **Doomsday: Last Survivors** su emulatori Android.

---

## 📋 Descrizione

Il bot gestisce in modo automatico le operazioni ripetitive del gioco su più istanze in parallelo:

- Raccolta messaggi (tab Alleanza e Sistema)
- Raccolta ricompense Alleanza (Negozio + Attività)
- Invio rifornimenti ad altri giocatori con gestione quota giornaliera
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
│       │       ├── rifornimento.py   ← eseguito in HOME prima della mappa
│       │       └── loop invio squadre
│       └── chiudi_istanza()
└── cleanup_istanze_appese()
```

---

## 📦 Moduli

| Modulo | Descrizione |
|--------|-------------|
| `main.py` | Entry point, pool con semaforo, loop principale |
| `raccolta.py` | Flusso raccolta risorse per singola istanza |
| `alleanza.py` | Automazione menu Alleanza/Dono |
| `messaggi.py` | Raccolta messaggi in-game |
| `rifornimento.py` | Invio rifornimenti ad altri giocatori (V5.12) |
| `bluestacks.py` | Gestione ciclo vita BlueStacks |
| `mumu.py` | Gestione ciclo vita MuMuPlayer 12 |
| `emulatore_base.py` | Logica comune condivisa tra emulatori |
| `adb.py` | Comandi ADB (tap, screenshot, keyevent) |
| `ocr.py` | Lettura testo da screenshot (Tesseract) |
| `stato.py` | Rilevamento stato gioco (home/mappa/overlay) |
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

### Rifornimento alleato (rifornimento.py V5.12)

```
controlla quota giornaliera (file JSON per istanza)
  └── quota esaurita? → skip fino alle 01:00 UTC
vai_in_home → leggi deposito OCR
  └── risorsa sotto soglia (10M)? → stop
seleziona risorsa (rotazione pomodoro/legno)
naviga Alleanza → Membri
  └── apri toggle R4/R3/R2/R1 (cerca avatar in parallelo)
trova FauMorfeus via template matching
apre maschera → legge tassa OCR → compila quantità → VAI
coda volo (timestamp + ETA) → calcolo attesa ottimale slot
  └── slot=0 → attendi rientro prima spedizione (non ETA fisso)
quota provviste=0 → salva stato su file
```

### Loop invio squadre raccolta

```
lettura contatore reale
  └── per ogni squadra da inviare:
        CERCA → OCR coordinate nodo
        ├── nodo in blacklist? → attendi / skip tipo
        └── nodo libero → TAP_NODO → prenota blacklist (RESERVED)
              → RACCOGLI → SQUADRA → MARCIA → COMMITTED
              → rileggi contatore reale
              ├── aumentato → squadra confermata ✅
              └── invariato → squadra respinta → rilascia blacklist 🔄
```

---

## ⏱️ Timing adattivo

- **EWMA** alpha=`0.3`
- **Outlier detection** z-score
- **Attesa minima:** `30 secondi`
- Stima aggiornata ad ogni ciclo per istanza

---

## 📁 Struttura file di output

```
C:\Bot-raccolta\V5\
├── bot.log                          # log principale
├── status.json                      # stato real-time per dashboard
├── timing.json                      # storico tempi di caricamento
├── rifornimento_stato_{nome}.json   # quota giornaliera per istanza
└── debug\
    └── ciclo_NNN\
        ├── report_ciclo_NNN.html
        └── *.png                    # screenshot diagnostici
```

---

## 🗂️ Contesto sessioni Claude

Questo repository include un file `CONTEXT.md` usato per mantenere il contesto
tra sessioni di sviluppo con Claude AI.

A inizio sessione dire a Claude: **"leggi il contesto"**

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
| V5.10 | OCR fail post-MARCIA: retry 3s; loop while invece di range fisso |
| V5.11 | rifornimento.py rebuild: template matching badge/frecce/avatar |
| V5.12 | rifornimento completo: coda volo, tassa OCR, quota giornaliera reset 01:00 UTC, flag abilitazione |
