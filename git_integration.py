# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Git-Integration

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any

CREATE_NO_WINDOW = 0x08000000


def _run(args: list[str], cwd: str, timeout: int = 10) -> subprocess.CompletedProcess:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "cwd": cwd,
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(args, **kwargs)


def git_ist_repo(projekt_pfad: str) -> bool:
    """Prüft, ob das Verzeichnis ein Git-Repository ist."""
    try:
        result = _run(["git", "rev-parse", "--git-dir"], projekt_pfad, timeout=5)
        return result.returncode == 0
    except Exception:
        return False


def git_status(projekt_pfad: str) -> dict:
    """Zeigt den Git-Status eines Projekts an."""
    try:
        result = _run(["git", "status", "--porcelain"], projekt_pfad)
        branch = _run(["git", "branch", "--show-current"], projekt_pfad, timeout=5).stdout.strip()
        aenderungen = []
        for zeile in (result.stdout or "").splitlines():
            if zeile:
                aenderungen.append({"status": zeile[:2], "datei": zeile[3:]})
        return {
            "erfolg": True,
            "branch": branch or "kein Branch",
            "aenderungen": aenderungen,
            "änderungen": aenderungen,
            "anzahl": len(aenderungen),
        }
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def git_commit(projekt_pfad: str, nachricht: str) -> dict:
    """Führt einen Git-Commit durch."""
    try:
        _run(["git", "add", "."], projekt_pfad)
        result = _run(["git", "commit", "-m", nachricht], projekt_pfad)
        return {
            "erfolg": result.returncode == 0,
            "ausgabe": (result.stdout or result.stderr or "").strip(),
        }
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def git_diff(projekt_pfad: str) -> dict:
    """Zeigt den Diff uncommitteter Änderungen an."""
    try:
        result = _run(["git", "diff"], projekt_pfad)
        return {"erfolg": True, "diff": result.stdout or "Keine Änderungen"}
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}


def git_branches(projekt_pfad: str) -> dict:
    """Listet alle Branches auf."""
    try:
        result = _run(["git", "branch", "-a"], projekt_pfad)
        return {
            "erfolg": True,
            "branches": [z.strip() for z in (result.stdout or "").splitlines() if z.strip()],
        }
    except Exception as e:
        return {"erfolg": False, "fehler": str(e)}
