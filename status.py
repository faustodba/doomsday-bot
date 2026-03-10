# ==============================================================================
#  DOOMSDAY BOT V5 - status.py
#  Scrive status.json in tempo reale per la dashboard web
#
#  Il file viene aggiornato ad ogni evento significativo:
#    - avvio/completamento istanza
#    - invio squadra
#    - lettura risorse deposito
#    - countdown prossimo ciclo
#
#  La dashboard.html legge questo file ogni 3s via fetch().
# ==============================================================================

import json
import os
import time
import threading
from datetime import datetime
import config

_lock       = threading.Lock()
_path       = os.path.join(config.BOT_DIR, "status.json")

# Stato in memoria — aggiornato dai vari moduli, scritto su disco atomicamente
_stato = {
    "ciclo":          0,
    "stato":          "idle",       # idle | running | waiting
    "countdown_s":    0,
    "ts_aggiornato":  "",
    "istanze":        {},           # { nome: { ... } }
    "storico_cicli":  [],           # ultimi 20 cicli
}

# Template stato istanza
def _istanza_default(nome: str) -> dict:
    return {
        "nome":           nome,
        "stato":          "attesa",  # attesa|avvio|caricamento|raccolta|completata|errore|timeout
        "squadre_inviate": 0,
        "squadre_target":  0,
        "pomodoro":        -1,
        "legno":           -1,
        "acciaio":         -1,
        "petrolio":        -1,
        "ocr_fail":        0,
        "cnt_errati":      0,
        "ts_inizio":       "",
        "durata_s":        0,
    }

# ------------------------------------------------------------------------------
# Scrittura atomica su disco
# ------------------------------------------------------------------------------
def _scrivi():
    _stato["ts_aggiornato"] = datetime.now().strftime("%H:%M:%S")
    tmp = _path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_stato, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path)
    except Exception:
        pass

# ------------------------------------------------------------------------------
# API pubblica
# ------------------------------------------------------------------------------

def init_ciclo(ciclo: int, nomi_istanze: list):
    """Inizializza stato per il nuovo ciclo, preservando storico istanze completate."""
    with _lock:
        _stato["ciclo"]       = ciclo
        _stato["stato"]       = "running"
        _stato["countdown_s"] = 0
        # Preserva le istanze completate/in errore dei cicli precedenti
        # Le istanze attive in questo ciclo vengono reinizializzate
        istanze_precedenti = _stato.get("istanze", {})
        nuove_istanze = {}
        for n in nomi_istanze:
            nuove_istanze[n] = _istanza_default(n)
        # Aggiunge le istanze dei cicli precedenti NON presenti in questo ciclo
        for n, ist in istanze_precedenti.items():
            if n not in nuove_istanze:
                nuove_istanze[n] = ist
        _stato["istanze"] = nuove_istanze
        _scrivi()


def istanza_avvio(nome: str):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["stato"]    = "avvio"
        ist["ts_inizio"] = datetime.now().strftime("%H:%M:%S")
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_caricamento(nome: str):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["stato"] = "caricamento"
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_raccolta(nome: str):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["stato"] = "raccolta"
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_risorse(nome: str, pomodoro: float, legno: float,
                    acciaio: float = -1, petrolio: float = -1):
    """Salva valori deposito letti dall'OCR."""
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["pomodoro"]  = round(pomodoro  / 1_000_000, 2) if pomodoro  > 0 else -1
        ist["legno"]     = round(legno     / 1_000_000, 2) if legno     > 0 else -1
        ist["acciaio"]   = round(acciaio   / 1_000_000, 2) if acciaio   > 0 else -1
        ist["petrolio"]  = round(petrolio  / 1_000_000, 2) if petrolio  > 0 else -1
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_target(nome: str, target: int):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["squadre_target"] = target
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_squadra_ok(nome: str):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["squadre_inviate"] += 1
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_ocr_fail(nome: str):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["ocr_fail"] += 1
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_cnt_errato(nome: str):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["cnt_errati"] += 1
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_completata(nome: str, inviate: int):
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["stato"]           = "completata"
        ist["squadre_inviate"] = inviate
        # Calcola durata
        try:
            t0 = datetime.strptime(ist["ts_inizio"], "%H:%M:%S").replace(
                year=datetime.now().year,
                month=datetime.now().month,
                day=datetime.now().day)
            ist["durata_s"] = int((datetime.now() - t0).total_seconds())
        except Exception:
            ist["durata_s"] = 0
        _stato["istanze"][nome] = ist
        _scrivi()


def istanza_errore(nome: str, tipo: str = "errore"):
    """tipo: 'errore' | 'timeout' | 'watchdog'"""
    with _lock:
        ist = _stato["istanze"].get(nome, _istanza_default(nome))
        ist["stato"] = tipo
        _stato["istanze"][nome] = ist
        _scrivi()


def ciclo_completato(ciclo: int, squadre: int, durata_s: int):
    """Aggiunge voce allo storico cicli (max 20)."""
    with _lock:
        _stato["storico_cicli"].append({
            "ciclo":    ciclo,
            "squadre":  squadre,
            "durata_m": round(durata_s / 60, 1),
            "ts":       datetime.now().strftime("%H:%M"),
        })
        if len(_stato["storico_cicli"]) > 20:
            _stato["storico_cicli"] = _stato["storico_cicli"][-20:]
        _scrivi()


def set_countdown(secondi: int):
    with _lock:
        _stato["stato"]       = "waiting"
        _stato["countdown_s"] = secondi
        _scrivi()


def set_stato(s: str):
    with _lock:
        _stato["stato"] = s
        _scrivi()
