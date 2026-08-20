# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Lokaler KI-Assistent

Nutzt Ollama zur Code-Generierung, -Analyse und -Optimierung.

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import config
import code_wrangler

try:
    import requests
except ImportError:  # Benötigt: pip install requests
    requests = None

CHAT_HISTORIE_DATEI = config.BASE_DIR / "CHAT_HISTORIE.json"
MAX_CHAT_EINTRAEGE = int(getattr(config, "KI_MAX_HISTORY", 100) or 100)
SYSTEM_HINWEIS = (
    "Du bist der lokale KI-Assistent der Legostein-Zentrale. "
    "Antworte auf Deutsch, konkret und hilfreich."
)


def chat_historie_laden() -> list[dict[str, Any]]:
    """Lädt die Chat-Historie aus der JSON-Datei."""
    if not CHAT_HISTORIE_DATEI.exists():
        return []
    try:
        daten = json.loads(CHAT_HISTORIE_DATEI.read_text(encoding="utf-8"))
        return daten if isinstance(daten, list) else []
    except (OSError, json.JSONDecodeError, TypeError):
        return []


def chat_historie_speichern(eintraege: list[dict[str, Any]]) -> None:
    """Speichert die Chat-Historie."""
    CHAT_HISTORIE_DATEI.write_text(
        json.dumps(eintraege[:MAX_CHAT_EINTRAEGE], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def chat_eintrag_hinzufuegen(
    rolle: str,
    inhalt: str,
    kontext: dict[str, Any] | None = None,
) -> None:
    """Fügt einen neuen Chat-Eintrag hinzu."""
    eintraege = chat_historie_laden()
    eintrag: dict[str, Any] = {
        "datum": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rolle": rolle,
        "inhalt": inhalt,
    }
    if kontext:
        eintrag["kontext"] = kontext
    eintraege.insert(0, eintrag)
    if len(eintraege) > MAX_CHAT_EINTRAEGE:
        eintraege = eintraege[:MAX_CHAT_EINTRAEGE]
    chat_historie_speichern(eintraege)


def chat_historie_loeschen() -> None:
    """Löscht die gesamte Chat-Historie."""
    CHAT_HISTORIE_DATEI.write_text("[]", encoding="utf-8")


def _timeout_sekunden() -> float:
    return float(getattr(config, "KI_TIMEOUT", 600) or 600)


def frage_an_ki(
    frage: str,
    kontext: str = "",
    modell: str | None = None,
    max_token: int | None = None,
) -> str:
    """Sendet eine Frage an Ollama und gibt die Antwort zurück.

    Kann mit oder ohne Kontext (Code, Projekt-Info) arbeiten.
    """
    if requests is None:
        return "FEHLER: requests-Bibliothek nicht installiert. Bitte: pip install requests"
    if not (frage or "").strip():
        return "FEHLER: Leere Frage."

    modell = modell or config.OLLAMA_MODELL
    token = int(max_token or getattr(config, "KI_MAX_TOKEN", 2048) or 2048)
    temperatur = float(getattr(config, "KI_TEMPERATURE", 0.7) or 0.7)
    if kontext:
        prompt = (
            f"{SYSTEM_HINWEIS}\n\n"
            f"Kontext (Code / Projekt-Info):\n{kontext}\n\n"
            f"Frage:\n{frage}"
        )
    else:
        prompt = f"{SYSTEM_HINWEIS}\n\n{frage}"

    payload = {
        "model": modell,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": token,
            "temperature": temperatur,
        },
    }
    try:
        antwort = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=_timeout_sekunden(),
        )
        antwort.raise_for_status()
        daten = antwort.json()
        return str(daten.get("response") or "Keine Antwort erhalten.").strip()
    except requests.exceptions.Timeout:
        sekunden = int(getattr(config, "KI_TIMEOUT", 600) or 600)
        return (
            f"FEHLER: Zeitüberschreitung ({sekunden}s).\n\n"
            "Mögliche Lösungen:\n"
            "1. Wähle ein kleineres Modell (z.B. llama3.2 statt qwen2.5)\n"
            "2. Erhöhe das KI-Timeout in den Einstellungen (⚙️)\n"
            "3. Stelle sicher, dass Ollama läuft und genug RAM hat\n\n"
            f"Aktuelles Modell: {modell}\n"
        )
    except requests.exceptions.ConnectionError:
        return "FEHLER: Ollama nicht erreichbar. Bitte in der Sidebar starten."
    except Exception as fehler:
        return f"FEHLER: {fehler}"


def code_generieren(
    beschreibung: str,
    sprache: str = "Python",
    kontext: str = "",
    modell: str | None = None,
) -> str:
    """Generiert Code basierend auf einer Beschreibung."""
    extra = f"\nBerücksichtige diesen Kontext:\n{kontext}\n" if kontext else ""
    prompt = (
        f"Generiere {sprache}-Code basierend auf dieser Beschreibung:\n\n"
        f"{beschreibung}\n"
        f"{extra}\n"
        f"Liefere NUR den Code, ohne Erklärungen. "
        f"Verwende einen fenced Code-Block (```{sprache.lower()})."
    )
    return frage_an_ki(prompt, kontext, modell)


def code_analysieren(
    code: str,
    frage: str = "Analysiere diesen Code. Was macht er? Gibt es Probleme?",
    modell: str | None = None,
) -> str:
    """Analysiert Code und beantwortet Fragen dazu."""
    prompt = (
        "Code:\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        f"Frage: {frage}\n\n"
        "Antworte auf Deutsch, konkret und hilfreich."
    )
    return frage_an_ki(prompt, code, modell)


def code_fixen(
    code: str,
    problem: str,
    modell: str | None = None,
) -> str:
    """Versucht, einen Code-Fehler zu beheben."""
    prompt = (
        "Der folgende Code hat ein Problem:\n\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        f"Problem: {problem}\n\n"
        "Bitte gib den korrigierten Code zurück. Liefere NUR den Code, keine Erklärungen.\n"
        "Verwende ```python für den Code-Block."
    )
    return frage_an_ki(prompt, code, modell)


def code_optimieren(
    code: str,
    ziel: str = "Geschwindigkeit und Lesbarkeit",
    modell: str | None = None,
) -> str:
    """Optimiert Code für Geschwindigkeit oder Lesbarkeit."""
    prompt = (
        f"Optimiere diesen Python-Code für {ziel}:\n\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        "Liefere den optimierten Code in einem ```python-Block.\n"
        "Füge eine kurze Erklärung der Änderungen hinzu."
    )
    return frage_an_ki(prompt, code, modell)


def projekt_frage(
    frage: str,
    projekt_pfad: str,
    modell: str | None = None,
) -> str:
    """Beantwortet Fragen über ein Projekt (liest Code-Analyse)."""
    steine = code_wrangler.analysiere_code(projekt_pfad)
    if not steine:
        return "Keine Code-Steine im Projekt gefunden."

    zusammenfassung = (
        f"Projekt: {Path(projekt_pfad).name}\n"
        f"Anzahl Steine: {len(steine)}\n\n"
        "Übersicht der Steine:\n"
    )
    for stein in steine[:20]:
        zusammenfassung += (
            f"\n- {stein.get('name')} ({stein.get('typ')}) in {stein.get('datei')}: "
            f"{stein.get('zeilen')} Zeilen, Ampel {stein.get('ampel')}"
        )

    prompt = (
        f"{zusammenfassung}\n\n"
        f"Frage zum Projekt: {frage}\n\n"
        "Antworte auf Deutsch, konkret und hilfreich."
    )
    return frage_an_ki(prompt, zusammenfassung, modell)


def code_erklären(
    code: str,
    zielgruppe: str = "Anfänger",
    modell: str | None = None,
) -> str:
    """Erklärt Code für eine bestimmte Zielgruppe."""
    prompt = (
        f"Erkläre diesen Python-Code für {zielgruppe}:\n\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        "Erklärung auf Deutsch, leicht verständlich, Schritt für Schritt."
    )
    return frage_an_ki(prompt, code, modell)


def code_umwandeln(
    code: str,
    zielsprache: str = "JavaScript",
    modell: str | None = None,
) -> str:
    """Wandelt Code von Python in eine andere Sprache um."""
    prompt = (
        f"Wandele diesen Python-Code in {zielsprache} um:\n\n"
        "```python\n"
        f"{code}\n"
        "```\n\n"
        f"Liefere NUR den {zielsprache}-Code, keine Erklärungen.\n"
        f"Verwende ```{zielsprache.lower()} für den Code-Block."
    )
    return frage_an_ki(prompt, code, modell)
