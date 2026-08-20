# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Projekt-Orchestrator

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import config

try:
    import requests
except ImportError:
    requests = None


def _name_saeubern(name: str) -> str:
    roh = "".join(ch if ch.isalnum() or ch in ("_", "-", " ") else "_" for ch in (name or "").strip())
    return re.sub(r"\s+", "_", roh).strip("_") or "neues_projekt"


def projekt_erstellen(idee: str, name: str) -> dict:
    """Erstellt ein komplettes Projekt aus einer Idee."""
    if requests is None:
        return {"erfolg": False, "fehler": "requests fehlt"}
    sicher = _name_saeubern(name)
    prompt = f"""
Erstelle einen detaillierten Projektplan für: {idee}

Projektname: {sicher}

Gib zurück als JSON:
{{
  "ordner": ["Ordner1", "Ordner2"],
  "dateien": [
    {{"pfad": "main.py", "inhalt": "..."}},
    {{"pfad": "requirements.txt", "inhalt": "..."}},
    {{"pfad": "README.md", "inhalt": "..."}}
  ]
}}

Liefere NUR das JSON, keine Erklärungen.
"""
    try:
        payload = {
            "model": config.OLLAMA_MODELL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 8192},
        }
        antwort = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=float(getattr(config, "KI_TIMEOUT", 600) or 600),
        )
        antwort.raise_for_status()
        plan_text = str(antwort.json().get("response") or "")
        json_match = re.search(r"\{.*\}", plan_text, re.DOTALL)
        if not json_match:
            return {"erfolg": False, "fehler": "Kein JSON im Plan gefunden"}
        plan = json.loads(json_match.group())
        if not isinstance(plan, dict):
            return {"erfolg": False, "fehler": "Ungültiger Plan"}

        config.PROJEKTE_DIR.mkdir(parents=True, exist_ok=True)
        projekt_pfad = config.PROJEKTE_DIR / sicher
        projekt_pfad.mkdir(parents=True, exist_ok=True)
        for ordner in plan.get("ordner") or []:
            (projekt_pfad / str(ordner)).mkdir(parents=True, exist_ok=True)
        erstellte_dateien = []
        for datei in plan.get("dateien") or []:
            rel = str(datei.get("pfad") or "").replace("\\", "/").lstrip("/")
            if not rel or ".." in Path(rel).parts:
                continue
            pfad = projekt_pfad / rel
            pfad.parent.mkdir(parents=True, exist_ok=True)
            pfad.write_text(str(datei.get("inhalt") or ""), encoding="utf-8")
            erstellte_dateien.append(str(pfad))
        if not erstellte_dateien:
            (projekt_pfad / "README.md").write_text(f"# {sicher}\n\n{idee}\n", encoding="utf-8")
            erstellte_dateien.append(str(projekt_pfad / "README.md"))
        return {
            "erfolg": True,
            "projekt": str(projekt_pfad),
            "dateien": erstellte_dateien,
        }
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}
