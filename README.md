# 🤖 Doomsday Bot V5

Bot Python per l'automazione della raccolta risorse nel gioco **Doomsday: Last Survivors** su emulatori Android.

---

## 📋 Descrizione

Il bot gestisce in modo automatico le operazioni ripetitive del gioco su più istanze in parallelo:

- Raccolta messaggi (tab Alleanza e Sistema) — **schedulata ogni 12 ore per istanza**
- Raccolta ricompense Alleanza (Negozio + Attività) — **schedulata ogni 12 ore per istanza**
- Invio rifornimenti a FauMorfeus con gestione quota giornaliera e **delta reale OCR**
- Ricerca e invio raccoglitori su nodi risorse (campo/segheria)
- Bilanciamento automatico delle risorse (pomodoro vs legno)
- Gestione blacklist nodi con **attesa dinamica basata su ETA marcia OCR**
- **OCR completo deposito:** pomodoro, legno, acciaio, petrolio, diamanti
- **Dashboard web** con dati storici persistenti tra riavvii

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
│       │       ├── messaggi.py    ← skip se <12h dall'ultima
│       │       ├── alleanza.py    ← skip se <12h dall'ultima
│       │       ├── rifornimento.py   ← HOME, delta reale OCR pre/post VAI
│       │       └── loop invio squadre (ETA marcia OCR, blacklist dinamica)
│       └── chiudi_istanza()
└── cleanup_istanze_appese()
```

---

## 📦 Moduli

| Modulo | Descrizione |
|--------|-------------|
| `main.py` | Entry point, pool con semaforo, loop principale |
| `raccolta.py` | Flusso raccolta risorse per singola istanza |
| `alleanza.py` | Automazione menu Alleanza/Dono — schedulata |
| `messaggi.py` | Raccolta messaggi in-game — schedulata |
| `rifornimento.py` | Invio rifornimenti con delta OCR reale |
| `scheduler.py` | **NUOVO** Schedulazione task periodici su file stato |
| `bluestacks.py` | Gestione ciclo vita BlueStacks |
| `mumu.py` | Gestione ciclo vita MuMuPlayer 12 |
| `emulatore_base.py` | Logica comune condivisa tra emulatori |
| `adb.py` | Comandi ADB (tap, screenshot, keyevent) |
| `ocr.py` | OCR Tesseract — risorse complete + ETA marcia |
| `stato.py` | Rilevamento stato gioco |
| `config.py` | Configurazione centralizzata |
| `timing.py` | EWMA adaptive timing |
| `log.py` | Logging centralizzato |
| `debug.py` | Screenshot diagnostici |
| `status.py` | status.json per dashboard — persistente tra riavvii |
| `report.py` | Report HTML a fine ciclo |
| `launcher.py` | GUI tkinter |
| `dashboard.html` | Dashboard web real-time |
| `dashboard_server.py` | HTTP server porta 8080 |

---

## 🔧 Requisiti

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [ADB](https://developer.android.com/tools/adb)
- BlueStacks 5+ e/o MuMuPlayer 12

```bash
pip install pillow pytesseract opencv-python
```

---

## 🚀 Avvio

```bash
cd C:\Bot-raccolta\V5

# Avvio bot
python main.py --emulatore 1

# Dashboard (finestra separata)
python dashboard_server.py
# Aprire: http://localhost:8080/dashboard.html
```

---

## 📊 Flusso raccolta per istanza

```
messaggi (se >12h) → alleanza (se >12h) → rifornimento → vai_in_mappa → squadre
```

### Schedulazione task (scheduler.py)
```
all'avvio task:
  leggi schedule_stato_{nome}_{porta}.json
  └── mai eseguito o >12h fa? → esegui → registra timestamp
  └── <12h fa? → skip con log "prossima tra Xh Ym"
```

### Rifornimento (rifornimento.py V5.12+)
```
controlla quota giornaliera → skip se esaurita
vai_in_home → leggi deposito OCR (PRE-invio)
seleziona risorsa → naviga Alleanza → Membri → trova FauMorfeus
apre maschera → VAI
leggi deposito OCR (POST-invio) → delta = PRE - POST → status.istanza_rifornimento()
coda volo → attesa ottimale slot
```

### Loop invio squadre
```
while attive < obiettivo:
  CERCA → OCR coordinate nodo → check blacklist
  tap nodo → RESERVED blacklist
  RACCOGLI → SQUADRA → leggi ETA marcia OCR → MARCIA
  rileggi contatore reale
  ├── aumentato → COMMITTED(ETA) ✅
  └── invariato → rollback blacklist 🔄
```

---

## 📈 Calcolo produzione

```
produzione_ciclo_N = (deposito_inizio_N+1 - deposito_inizio_N) + inviato_N
```
Disponibile dal 2° ciclo in poi. Visibile nella dashboard per istanza e aggregato nello storico.

---

## 📊 Dashboard

Sezioni principali:
- **Riepilogo** — contatori stato istanze
- **Risorse totali** — aggregato depositi (pomodoro/legno/acciaio/petrolio/💎 diamanti)
- **Inviato FauMorfeus** — aggregato invii ciclo corrente
- **Stato istanze** — card con deposito, produzione, inviato, errori
- **Storico cicli** — produzione e inviato aggregati per ciclo

> Al riavvio del bot le card mostrano i dati dell'ultimo ciclo con badge **"storico DD/MM HH:MM"**.

---

## 📁 File di output runtime

```
C:\Bot-raccolta\V5\
├── bot.log
├── status.json
├── timing.json
├── rifornimento_stato_{nome}_{porta}.json
├── schedule_stato_{nome}_{porta}.json       ← NUOVO
└── debug\ciclo_NNN\
    ├── report_ciclo_NNN.html
    └── *.png
```

---

## 📜 Storico versioni

| Versione | Note |
|----------|------|
| V2 | AutoHotkey — 14 istanze Sandboxie |
| V3 | Python, singolo emulatore |
| V4 | Multithreading, multi-emulatore, MuMu |
| V5 | Alleanza, messaggi, rifornimento, launcher, dashboard |
| V5.9 | Blacklist, lettura reale post-MARCIA |
| V5.10 | Loop while, OCR retry |
| V5.11 | rifornimento template matching |
| V5.12 | Rifornimento completo, quota giornaliera |
| V5.13 | Blacklist RESERVED/COMMITTED |
| V5.13.2 | ETA marcia OCR, attesa dinamica |
| V5.14 | OCR completo deposito, produzione inter-ciclo, schedulazione 12h, dashboard storico+diamanti+inviato |

---

## 🗂️ Contesto sessioni Claude

```
# A inizio sessione:
"leggi il contesto"
# Claude fa web_fetch su CONTEXT.md
```
