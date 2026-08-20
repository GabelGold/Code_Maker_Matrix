# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Agenten-Manager

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import config
import code_wrangler

try:
    import requests
except ImportError:
    requests = None

SUBAGENTEN = {
    "explorer": {
        "name": "📊 Code-Explorer",
        "beschreibung": "Durchsucht das Projekt nach Mustern und Strukturen",
        "prompt": "Du bist ein Code-Explorer. Analysiere das Projekt und finde: {aufgabe}",
    },
    "tester": {
        "name": "🧪 Test-Generator",
        "beschreibung": "Erstellt automatisch Unit-Tests",
        "prompt": "Du bist ein Test-Experte. Schreibe Unit-Tests für: {aufgabe}",
    },
    "doc_writer": {
        "name": "📝 Doc-Writer",
        "beschreibung": "Generiert Docstrings und READMEs",
        "prompt": "Du bist ein Dokumentations-Spezialist. Schreibe Doku für: {aufgabe}",
    },
    "refactor": {
        "name": "🔧 Refactor-Agent",
        "beschreibung": "Optimiert Code-Strukturen",
        "prompt": "Du bist ein Refactoring-Experte. Optimiere: {aufgabe}",
    },
    "bug_hunter": {
        "name": "🐛 Bug-Hunter",
        "beschreibung": "Sucht nach potentiellen Fehlern",
        "prompt": "Du bist ein Bug-Hunter. Finde Fehler in: {aufgabe}",
    },
    "architect": {
        "name": "🏗️ Architekt",
        "beschreibung": "Entwirft System-Architekturen",
        "prompt": "Du bist ein System-Architekt. Entwirf: {aufgabe}",
    },
}


def verfuegbare_agenten() -> list[dict]:
    """Gibt die Liste aller verfügbaren Agenten zurück."""
    return [
        {"id": k, "name": v["name"], "beschreibung": v["beschreibung"]}
        for k, v in SUBAGENTEN.items()
    ]


def _agent_call(agent_name: str, prompt: str) -> str:
    """Führt einen Agenten-Aufruf durch."""
    if requests is None:
        return f"Fehler bei Agent {agent_name}: requests fehlt (pip install requests)"
    try:
        payload = {
            "model": config.OLLAMA_MODELL,
            "prompt": f"{prompt}\n\nAntworte auf Deutsch, konkret und hilfreich.",
            "stream": False,
            "options": {"num_predict": int(getattr(config, "KI_MAX_TOKEN", 2048) or 2048)},
        }
        antwort = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=float(getattr(config, "KI_TIMEOUT", 600) or 600),
        )
        antwort.raise_for_status()
        return str(antwort.json().get("response") or "Keine Antwort erhalten.")
    except Exception as e:
        return f"Fehler bei Agent {agent_name}: {e}"


def starte_agenten_mission(
    aufgabe: str,
    projekt_pfad: str,
    agenten: list[str] | None = None,
    parallel: bool = True,
) -> dict[str, Any]:
    """Startet eine Agenten-Mission mit Subagenten."""
    if agenten is None:
        agenten = list(SUBAGENTEN.keys())
    agenten = [a for a in agenten if a in SUBAGENTEN]
    if not agenten:
        agenten = list(SUBAGENTEN.keys())

    steine = code_wrangler.analysiere_code(projekt_pfad) if projekt_pfad else []
    projektdaten = (
        f"Projekt: {projekt_pfad}\n"
        f"Anzahl Steine: {len(steine)}\n"
        f"Steine: {', '.join([s.get('name', '?') for s in steine[:20]])}"
    )
    ergebnisse: dict[str, Any] = {}

    def _lauf(agent_name: str) -> str:
        agent = SUBAGENTEN[agent_name]
        prompt = agent["prompt"].format(aufgabe=aufgabe + "\n\n" + projektdaten)
        return _agent_call(agent_name, prompt)

    if parallel and len(agenten) > 1:
        with ThreadPoolExecutor(max_workers=min(len(agenten), 4)) as executor:
            futures = {executor.submit(_lauf, name): name for name in agenten}
            for future in as_completed(futures):
                agent_name = futures[future]
                try:
                    ergebnisse[agent_name] = {
                        "erfolg": True,
                        "ergebnis": future.result(timeout=int(getattr(config, "KI_TIMEOUT", 600) or 600)),
                    }
                except Exception as e:
                    ergebnisse[agent_name] = {"erfolg": False, "fehler": str(e)}
    else:
        for agent_name in agenten:
            try:
                ergebnisse[agent_name] = {"erfolg": True, "ergebnis": _lauf(agent_name)}
            except Exception as e:
                ergebnisse[agent_name] = {"erfolg": False, "fehler": str(e)}

    return {
        "mission": aufgabe,
        "projekt": projekt_pfad,
        "datum": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ergebnisse": ergebnisse,
    }
