# Doomsday Bot V5 — CONTEXT FILE
> Aggiorna questo file a fine di ogni sessione produttiva e fai `git push`.
> Claude legge questo file all'inizio di ogni sessione tramite web_fetch.

---

## Repository
- **URL:** https://github.com/faustodba/doomsday-bot
- **Branch principale:** main
- **Percorso locale:** `C:\Bot-raccolta\V5`

---

## Panoramica progetto

Bot Python per l'automazione del gioco **Doomsday: Last Survivors** su emulatori Android (BlueStacks e MuMuPlayer 12). Supporta multi-istanza con esecuzione parallela controllata da semaforo.

---

## Architettura V5

### Istanze configurate
- **FAU_00, FAU_01, FAU_02, FAU_03, FAU_04, FAU_05, FAU_07, FAU_08** (8 istanze totali)
- Max **2 istanze in parallelo** (semaforo)
- Cicli da **10 minuti**
- Timeout per istanza: **180 secondi**

### Emulatori supportati
- **BlueStacks** — avviato e stoppato per ogni ciclo
- **MuMuPlayer 12** — integrato con Provider Pattern (`config.ADB_EXE`)
- Modulo condiviso: `emulatore_base.py` (elimina duplicazione di codice)

### Risoluzione di riferimento
- **960x540** (coordinate normalizzate su questa risoluzione)

---

## Moduli principali

| Modulo | Descrizione |
|--------|-------------|
| `main.py` | Entry point, argomenti `--istanze` / `--emulatore` (retrocompat) |
| `raccolta.py` | Flusso principale raccolta risorse (V5.7) |
| `alleanza.py` | Automazione menu Alleanza/Dono |
| `messaggi.py` | Gestione messaggi in-game |
| `rifornimento.py` | Invio rifornimenti ad altri giocatori (V5.2) |
| `bluestacks.py` | Gestione ciclo vita BlueStacks |
| `mumu.py` | Gestione ciclo vita MuMuPlayer 12 |
| `emulatore_base.py` | Modulo base condiviso tra emulatori |
| `adb.py` | Comandi ADB (tap, screenshot, keycode) |
| `ocr.py` | Lettura testo da screenshot (Tesseract) |
| `stato.py` | Macchina a stati per ogni istanza |
| `config.py` | Configurazione centralizzata (coordinate, soglie, percorsi) |
| `timing.py` | EWMA adaptive timing (alpha=0.3, outlier z-score detection) |
| `log.py` | Logging centralizzato |
| `debug.py` | Utilities debug, `debug.init_ciclo(ciclo)` |
| `status.py` | Scrittura `status.json` per dashboard |
| `report.py` | Generazione report sessione |
| `launcher.py` | GUI tkinter: radio BS/MuMu, checkbox istanze, stato real-time |

### File di test presenti nel repo
`test_alleanza.py`, `test_coordinate.py`, `test_coordinate2.py`, `test_messaggi.py`,
`test_mumu.py`, `test_ocr.py`, `test_ocr_nodo.py`, `test_rifornimento.py`, `test_tap.py`

### File patch presenti nel repo
`main_patch_blacklist.py`, `ocr_patch_leggi_coordinate_nodo.py`

---

## Flusso raccolta_istanza (ordine esecuzione)

```
messaggi → alleanza → rifornimento → vai_in_mappa → raccolta risorse
```

---

## Coordinate principali (960x540)

### alleanza.py
| Costante | Valore |
|----------|--------|
| `COORD_ALLEANZA` | (760, 505) |
| `COORD_DONO` | (877, 458) |
| `COORD_TAB_NEGOZIO` | (810, 75) |
| `COORD_TAB_ATTIVITA` | (600, 75) |
| `COORD_RIVENDICA` | (856, 240) |
| `COORD_RACCOGLI_TUTTO` | (856, 505) |
| `RIVENDICA_CLICK` | 10 (click singoli, è a pagamento) |

**Flusso alleanza:** Alleanza → Dono → Negozio (Rivendica x10 singoli) → Attività (Raccogli tutto, gratis) → Back x3
> Il menu Dono si apre già sul tab Negozio.

### OCR nodo (blacklist)
| Costante | Valore |
|----------|--------|
| `TAP_LENTE_COORD` | (380, 18) |
| Zona OCR coordinate X | (430, 125, 530, 155) |
| Zona OCR coordinate Y | (535, 125, 635, 155) |
| Zona OCR nodo (fix) | (240, 12, 380, 25) + OTSU |

**Flusso blacklist:** CERCA → sleep 1.5s → tap lente → sleep 0.8s → screenshot → OCR → check blacklist → tap nodo (chiude popup) oppure tap lente grande se in blacklist

> ⚠️ Problema noto: `cx=None` occasionale — fix: aumentare delay dopo TAP_LENTE_COORD (attualmente 800ms)

### rifornimento.py
| Costante | Valore |
|----------|--------|
| `RIFORNIMENTO_DESTINATARIO` | configurabile in config.py |
| `RIFORNIMENTO_SOGLIA_M` | 10.0 |
| `RIFORNIMENTO_AVATAR` | template matching crop (147,278,204,328), soglia 0.75 |
| OCR pulsante | x=443, y variabile |

---

## Logica timing (timing.py)
- **EWMA** alpha=0.3
- **Outlier detection** z-score
- **Wait minimo:** 30 secondi prima del polling adattivo

---

## Logica reset / watchdog
- **Banner dismissal:** 3× KEYCODE_BACK con conferma
- **OCR-fail reset post-march:** max 5 tentativi
- **Watchdog:** crash detection + restart automatico
- **Timeout per istanza:** 180s

---

## Screenshot e OCR
- Screenshot effettuato **PRIMA** del tap sul nodo (raccolta.py V5.5+)
- OCR zona nodo: coordinata con metodo OTSU

---

## launcher.py (GUI tkinter)
- Radio button: BlueStacks / MuMuPlayer
- Checkbox per selezione istanze (da config.py)
- Stato real-time via `status.json`
- Dashboard HTML con auto-refresh ogni 3 secondi

> ⚠️ **Problema aperto:** launcher non funziona — errore in `bluestacks.py` → `emulatore_base.py` → `attendi_e_raccogli_istanza`

---

## Problemi aperti / Da risolvere
- [ ] **Launcher** non funzionante (vedi sopra)
- [ ] **cx=None** occasionale nella blacklist nodi (aumentare delay TAP_LENTE)

---

## Decisioni architetturali già prese (non ridiscutere)
- **Provider Pattern** per selezione ADB exe (`config.ADB_EXE`)
- **emulatore_base.py** come modulo condiviso tra BlueStacks e MuMu
- **Semaforo** per limitare a max 2 istanze parallele
- **EWMA** per adaptive timing (non usare sleep fissi)
- **Screenshot PRIMA del tap** sul nodo per OCR affidabile

---

## Storico versioni principali
| Versione | Note |
|----------|------|
| V2 | AutoHotkey — 14 istanze Sandboxie, stabile |
| V3 | Migrazione Python, singolo emulatore |
| V4 | Multithreading, multi-emulatore, MuMu integration |
| V5 | Aggiunta alleanza, messaggi, rifornimento, launcher, dashboard |
| V5.5 | Screenshot prima del tap nodo |
| V5.6 | raccolta.py refactor |
| V5.7 | rifornimento integrato nel flusso principale |

---

## Come usare questo file a inizio sessione
Dire a Claude: **"leggi il contesto"**
Claude eseguirà:
```
web_fetch → https://raw.githubusercontent.com/faustodba/doomsday-bot/main/CONTEXT.md
```

---

*Ultimo aggiornamento: 2026-03-10*
