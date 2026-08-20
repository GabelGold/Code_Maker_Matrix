# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Skill-Loader

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import json
from typing import Any

import config

try:
    import yaml
except ImportError:
    yaml = None

SKILLS_DIR = config.BASE_DIR / "SKILLS"


def skills_laden() -> list[dict]:
    """Lädt alle verfügbaren Skills aus dem SKILLS-Ordner."""
    skills: list[dict] = []
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    for datei in SKILLS_DIR.iterdir():
        if datei.suffix.lower() in (".yaml", ".yml"):
            if yaml is None:
                continue
            try:
                skill = yaml.safe_load(datei.read_text(encoding="utf-8"))
                if isinstance(skill, dict):
                    skill["_datei"] = datei.name
                    skills.append(skill)
            except Exception:
                pass
        elif datei.suffix.lower() == ".json":
            try:
                skill = json.loads(datei.read_text(encoding="utf-8"))
                if isinstance(skill, dict):
                    skill["_datei"] = datei.name
                    skills.append(skill)
            except Exception:
                pass
    return skills


def skill_ausfuehren(skill: dict, code: str, context: str = "") -> dict:
    """Führt einen Skill auf einem Code-Block aus."""
    try:
        import requests
    except ImportError:
        return {"skill": skill.get("name", "Unbekannt"), "ergebnisse": [{"erfolg": False, "fehler": "requests fehlt"}]}

    ergebnisse: list[dict[str, Any]] = []
    for schritt in skill.get("schritte") or []:
        prompt = str(schritt.get("ki_anfrage") or "")
        prompt = prompt.replace("{code}", code).replace("{context}", context)
        try:
            payload = {
                "model": config.OLLAMA_MODELL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 4096},
            }
            antwort = requests.post(
                config.OLLAMA_URL,
                json=payload,
                timeout=float(getattr(config, "KI_TIMEOUT", 600) or 600),
            )
            antwort.raise_for_status()
            ergebnisse.append(
                {
                    "schritt": schritt.get("name", "Unbekannt"),
                    "erfolg": True,
                    "ergebnis": antwort.json().get("response", ""),
                }
            )
        except Exception as e:
            ergebnisse.append(
                {
                    "schritt": schritt.get("name", "Unbekannt"),
                    "erfolg": False,
                    "fehler": str(e),
                }
            )
    return {"skill": skill.get("name", "Unbekannt"), "ergebnisse": ergebnisse}
