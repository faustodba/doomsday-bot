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
| `raccolta.py` | Flusso principale raccolta risorse |
| `alleanza.py` | Automazione menu Alleanza/Dono |
| `messaggi.py` | Gestione messaggi in-game |
| `rifornimento.py` | Invio rifornimenti ad altri giocatori (V5.12) |
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
`test_mumu.py`, `test_ocr.py`, `test_ocr_nodo.py`, `test_rifornimento.py`,
`test_rifornimento_steps.py`, `test_tap.py`

### File patch presenti nel repo
`main_patch_blacklist.py`, `ocr_patch_leggi_coordinate_nodo.py`

---

## Flusso raccolta_istanza (ordine esecuzione)

```
messaggi → alleanza → rifornimento (in HOME) → vai_in_mappa → raccolta risorse
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

### rifornimento.py (V5.12)
| Costante | Valore |
|----------|--------|
| `RIFORNIMENTO_DESTINATARIO` | configurabile in config.py |
| `RIFORNIMENTO_SOGLIA_M` | 10.0M — non invia se deposito sotto soglia |
| `RIFORNIMENTO_QTA_*` | valore alto (es. 999M) — il gioco applica il cap automaticamente |
| `RIFORNIMENTO_ABILITATO` | True/False — flag abilitazione in config.py |
| Reset quota giornaliera | 01:00 UTC — stato salvato in `rifornimento_stato_{nome}.json` |

**Flusso rifornimento:**
1. Controlla quota giornaliera (`rifornimento_stato_{nome}.json`) — skip se esaurita
2. `vai_in_home` + legge deposito reale via OCR
3. Seleziona risorsa con rotazione (pomodoro → legno → pomodoro...)
4. Naviga Alleanza → Membri → apre toggle R4/R3/R2/R1 (cerca avatar in parallelo)
5. Trova avatar FauMorfeus via template matching
6. Apre maschera → legge tassa OCR → compila quantità → VAI
7. Coda volo `deque(timestamp, eta_ar)` per calcolo attesa ottimale slot
8. Quando provviste = 0 → salva stato quota esaurita su file

---

## Logica raccolta risorse (raccolta.py)

### Loop invio squadre
- **Loop `while`**: continua finché `attive_correnti < obiettivo` (obiettivo = totale slot)
- **Lettura reale** del contatore squadre dopo ogni MARCIA (non calcolo progressivo)
- **Max 3 fallimenti consecutivi** prima di abbandonare — reset ad ogni conferma squadra
- **Blacklist TTL fisso:** 120s — il nodo NON viene rimosso alla conferma marcia
- **Blacklist rilasciata** se errore prima del tap MARCIA (marcia_inviata=False)
- **Blacklist rilasciata** se squadra respinta (contatore invariato dopo retry)
- **OCR fail post-MARCIA:** retry dopo 3s prima di contare come fallimento
- **Tipi bloccati:** se nodo sempre in blacklist per un tipo → skip tutte le squadre di quel tipo
- **Uscita anticipata** se tutti i tipi disponibili sono bloccati

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

## launcher.py (GUI tkinter)
- Radio button: BlueStacks / MuMuPlayer
- Checkbox per selezione istanze (da config.py)
- Stato real-time via `status.json`
- Dashboard HTML con auto-refresh ogni 3 secondi

> ⚠️ **Problema aperto:** launcher non funzionante — errore in `bluestacks.py` → `emulatore_base.py` → `attendi_e_raccogli_istanza`

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
- **Loop while** per raccolta (non range fisso) — continua finché slot liberi
- **Lettura reale** contatore post-MARCIA (non calcolo progressivo)
- **3 fallimenti consecutivi** come soglia abbandono raccolta
- **Quantità rifornimento alta** in config (es. 999M) — il gioco applica il cap, il bot non deve calcolarlo
- **Tassa rifornimento letta OCR** dalla maschera ad ogni spedizione (non hardcodata)
- **Quota giornaliera** salvata su file per istanza — reset automatico alle 01:00 UTC

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
| V5.8 | Fix blacklist TTL, fix report TypeError, fix cleanup PID |
| V5.9 | Fix blacklist: prenotata dopo tap nodo, rilasciata su errore; lettura reale post-MARCIA; max 3 fallimenti consecutivi |
| V5.10 | OCR fail post-MARCIA: retry 3s; loop while invece di range fisso |
| V5.11 | rifornimento.py rebuild: template matching badge/frecce/avatar |
| V5.12 | rifornimento completo: coda volo timestamp, tassa OCR, quota giornaliera con reset 01:00 UTC, flag RIFORNIMENTO_ABILITATO |

---

## Come usare questo file a inizio sessione
Dire a Claude: **"leggi il contesto"**
Claude eseguirà:
```
web_fetch → https://raw.githubusercontent.com/faustodba/doomsday-bot/main/CONTEXT.md
```

---

*Ultimo aggiornamento: 2026-03-13*
