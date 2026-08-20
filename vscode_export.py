# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – VS-Code-Export

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def in_vscode_oeffnen(projekt_pfad: str) -> dict:
    """Öffnet das Projekt in VS Code."""
    if not projekt_pfad:
        return {"erfolg": False, "meldung": "Kein Projektpfad angegeben"}
    binary = shutil.which("code") or shutil.which("code.cmd")
    try:
        if binary:
            result = subprocess.run([binary, projekt_pfad], capture_output=True, timeout=8)
            if result.returncode == 0:
                return {"erfolg": True, "meldung": "VS Code gestartet"}
        if os.name == "nt":
            subprocess.Popen(["cmd", "/c", "code", projekt_pfad], shell=False)
            return {"erfolg": True, "meldung": "VS Code Start ausgelöst"}
        result = subprocess.run(["code", projekt_pfad], capture_output=True, timeout=8)
        return {
            "erfolg": result.returncode == 0,
            "meldung": "VS Code gestartet" if result.returncode == 0 else "VS Code nicht gefunden",
        }
    except FileNotFoundError:
        return {"erfolg": False, "meldung": "VS Code nicht im PATH gefunden"}
    except Exception as e:
        return {"erfolg": False, "meldung": f"Fehler: {e}"}


def workspace_erstellen(projekt_pfad: str) -> dict:
    """Erstellt eine .code-workspace-Datei für das Projekt."""
    wurzel = Path(projekt_pfad)
    workspace = {
        "folders": [{"path": str(wurzel.resolve())}],
        "settings": {
            "python.defaultInterpreterPath": "python",
            "files.autoSave": "onFocusChange",
        },
    }
    pfad = wurzel / f"{wurzel.name}.code-workspace"
    try:
        pfad.write_text(json.dumps(workspace, indent=2), encoding="utf-8")
        return {"erfolg": True, "pfad": str(pfad)}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}
