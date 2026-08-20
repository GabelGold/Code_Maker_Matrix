# -*- coding: utf-8 -*-
"""Zentrale Pfade und Grenzen der Legostein-Fabrik v6.0 Reality-Edition."""

from __future__ import annotations

import json
import pathlib
from typing import Any

BASE_DIR = pathlib.Path(__file__).parent
PROJEKTE_DIR = BASE_DIR / "PROJEKTE"
ZEITMASCHINE_DIR = BASE_DIR / "ZEITMASCHINE"
SANDBOX_DIR = BASE_DIR / "SANDBOX"
BERICHTE_DIR = BASE_DIR / "BERICHTE"

IGNORE_LIST = ["venv", "__pycache__", "node_modules", ".git", ".idea"]
MAX_BACKUPS = 5
DIFF_SCHWELLE = 20

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_TIMEOUT = 5
OLLAMA_MODELL = "llama3.2"
MAX_NACHBARN = 3

# KI-Assistent
KI_MAX_HISTORY = 100
KI_TEMPERATURE = 0.7
KI_MAX_TOKEN = 2048
KI_TIMEOUT = 600

SETTINGS_DATEI = BASE_DIR / "settings.json"
PROMPT_HISTORIE_DATEI = BASE_DIR / "PROMPT_HISTORIE.json"


def _pfade_setzen(basis: pathlib.Path) -> None:
    global BASE_DIR, PROJEKTE_DIR, ZEITMASCHINE_DIR, SANDBOX_DIR, BERICHTE_DIR
    global SETTINGS_DATEI, PROMPT_HISTORIE_DATEI
    BASE_DIR = pathlib.Path(basis)
    PROJEKTE_DIR = BASE_DIR / "PROJEKTE"
    ZEITMASCHINE_DIR = BASE_DIR / "ZEITMASCHINE"
    SANDBOX_DIR = BASE_DIR / "SANDBOX"
    BERICHTE_DIR = BASE_DIR / "BERICHTE"
    SETTINGS_DATEI = BASE_DIR / "settings.json"
    PROMPT_HISTORIE_DATEI = BASE_DIR / "PROMPT_HISTORIE.json"


def einstellungen_als_dict() -> dict[str, Any]:
    return {
        "base_dir": str(BASE_DIR),
        "ollama_host": OLLAMA_HOST,
        "ollama_modell": OLLAMA_MODELL,
        "ollama_timeout": OLLAMA_TIMEOUT,
        "max_backups": int(MAX_BACKUPS),
        "max_nachbarn": int(MAX_NACHBARN),
        "diff_schwelle": int(DIFF_SCHWELLE),
        "ki_timeout": int(KI_TIMEOUT),
    }


def einstellungen_anwenden(daten: dict[str, Any]) -> None:
    global MAX_BACKUPS, MAX_NACHBARN, DIFF_SCHWELLE, OLLAMA_HOST, OLLAMA_URL
    global OLLAMA_MODELL, OLLAMA_TIMEOUT, KI_TIMEOUT
    # BASE_DIR bleibt immer der Ordner von config.py – sonst bricht Portabilität.
    if daten.get("ollama_host"):
        OLLAMA_HOST = str(daten["ollama_host"]).rstrip("/")
        OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"
    if daten.get("ollama_modell"):
        OLLAMA_MODELL = str(daten["ollama_modell"])
    if daten.get("ollama_timeout") is not None:
        OLLAMA_TIMEOUT = int(daten["ollama_timeout"])
    if daten.get("max_backups") is not None:
        MAX_BACKUPS = max(1, int(daten["max_backups"]))
    if daten.get("max_nachbarn") is not None:
        MAX_NACHBARN = max(1, int(daten["max_nachbarn"]))
    if daten.get("diff_schwelle") is not None:
        DIFF_SCHWELLE = max(1, int(daten["diff_schwelle"]))
    if daten.get("ki_timeout") is not None:
        KI_TIMEOUT = max(30, min(1200, int(daten["ki_timeout"])))


def einstellungen_laden() -> dict[str, Any]:
    if not SETTINGS_DATEI.exists():
        return einstellungen_als_dict()
    try:
        daten = json.loads(SETTINGS_DATEI.read_text(encoding="utf-8"))
        if isinstance(daten, dict):
            einstellungen_anwenden(daten)
            return einstellungen_als_dict()
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return einstellungen_als_dict()


def einstellungen_speichern(daten: dict[str, Any] | None = None) -> pathlib.Path:
    if daten:
        einstellungen_anwenden(daten)
    aktuell = einstellungen_als_dict()
    SETTINGS_DATEI.write_text(
        json.dumps(aktuell, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _config_py_aktualisieren(aktuell)
    return SETTINGS_DATEI


def _config_py_aktualisieren(daten: dict[str, Any]) -> None:
    """Schreibt die geänderten Konstanten zurück nach config.py, Rest bleibt unberührt."""
    pfad = pathlib.Path(__file__)
    try:
        text = pfad.read_text(encoding="utf-8")
    except OSError:
        return
    ersetzungen = {
        "MAX_BACKUPS": f'MAX_BACKUPS = {int(daten["max_backups"])}',
        "DIFF_SCHWELLE": f'DIFF_SCHWELLE = {int(daten["diff_schwelle"])}',
        "OLLAMA_HOST": f'OLLAMA_HOST = "{daten["ollama_host"]}"',
        "OLLAMA_MODELL": f'OLLAMA_MODELL = "{daten["ollama_modell"]}"',
        "MAX_NACHBARN": f'MAX_NACHBARN = {int(daten["max_nachbarn"])}',
        "KI_TIMEOUT": f'KI_TIMEOUT = {int(daten.get("ki_timeout", 600))}',
    }
    zeilen = text.splitlines(keepends=True)
    neu: list[str] = []
    for zeile in zeilen:
        eingerueckt = zeile[:1] in " \t"
        kern = zeile.split("#", 1)[0].strip()
        ersetzt = False
        if not eingerueckt:
            for name, zuweisung in ersetzungen.items():
                if kern.startswith(name + " ="):
                    endung = "\n" if zeile.endswith("\n") else ""
                    neu.append(zuweisung + endung)
                    ersetzt = True
                    break
        if not ersetzt:
            neu.append(zeile)
    gekoppelt: list[str] = []
    for zeile in neu:
        eingerueckt = zeile[:1] in " \t"
        kern = zeile.split("#", 1)[0].strip()
        if not eingerueckt and kern.startswith("OLLAMA_URL ="):
            endung = "\n" if zeile.endswith("\n") else ""
            gekoppelt.append('OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"' + endung)
        else:
            gekoppelt.append(zeile)
    try:
        pfad.write_text("".join(gekoppelt), encoding="utf-8")
    except OSError:
        pass


def historie_laden() -> list[dict[str, Any]]:
    if not PROMPT_HISTORIE_DATEI.exists():
        return []
    try:
        daten = json.loads(PROMPT_HISTORIE_DATEI.read_text(encoding="utf-8"))
        return daten if isinstance(daten, list) else []
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def historie_hinzufuegen(eintrag: dict[str, Any]) -> None:
    liste = historie_laden()
    liste.insert(0, eintrag)
    liste = liste[:200]
    PROMPT_HISTORIE_DATEI.write_text(
        json.dumps(liste, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def historie_loeschen() -> None:
    PROMPT_HISTORIE_DATEI.write_text("[]", encoding="utf-8")


einstellungen_laden()
