# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – GitHub-Explorer

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import config  # <-- NEU: Für Token und Repo-Infos

GITHUB_REPO = config.GITHUB_REPO       # aus config.py
GITHUB_OWNER = config.GITHUB_OWNER     # aus config.py
GITHUB_API = "https://api.github.com"

try:
    import requests
except ImportError:
    requests = None


# ─── BESTEHENDE FUNKTIONEN ───

def get_repo_content(path: str = "") -> dict[str, Any]:
    """Holt den Inhalt eines Pfads aus dem GitHub-Repository."""
    if requests is None:
        return {"typ": "error", "fehler": "requests fehlt. Bitte: pip install requests"}
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and "content" in data:
            content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            return {
                "typ": "file",
                "name": data.get("name", path),
                "pfad": data.get("path", path),
                "inhalt": content,
                "groesse": data.get("size", 0),
                "url": data.get("html_url", ""),
            }
        if isinstance(data, list):
            items = []
            for item in data:
                items.append(
                    {
                        "name": item.get("name", ""),
                        "pfad": item.get("path", ""),
                        "typ": "folder" if item.get("type") == "dir" else "file",
                        "url": item.get("html_url", ""),
                    }
                )
            return {"typ": "folder", "pfad": path or "/", "items": items}
        return {"typ": "unknown", "fehler": "Unbekanntes Format"}
    except Exception as e:
        return {"typ": "error", "fehler": str(e)}


def get_readme() -> str:
    """Holt die README.md aus dem Repository, Fallback README_CMM.md."""
    for name in ("README.md", "README_CMM.md"):
        result = get_repo_content(name)
        if result.get("typ") == "file":
            return result.get("inhalt") or ""
    return "README.md konnte nicht geladen werden."


def get_repo_structure(path: str = "") -> list[dict]:
    """Holt die Ordnerstruktur des Repositorys."""
    result = get_repo_content(path)
    if result.get("typ") == "folder":
        return result.get("items") or []
    return []


# ─── NEU: CMM VERÖFFENTLICHT SICH SELBST ───

def cmm_auf_github_veroeffentlichen() -> dict:
    """
    Veröffentlicht CMM auf GitHub – automatisch mit dem in config.py hinterlegten Token.
    
    Returns:
        dict mit Status und Details
    """
    if requests is None:
        return {"fehler": "requests fehlt. Bitte: pip install requests"}

    # Token aus config lesen
    token = getattr(config, "GITHUB_TOKEN", None)
    if not token:
        return {"fehler": "Kein GitHub-Token in config.py gefunden. Bitte GITHUB_TOKEN setzen."}

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    owner = GITHUB_OWNER
    repo = GITHUB_REPO

    ergebnis = {
        "repository": False,
        "dateien": [],
        "release": False,
        "fehler": []
    }

    # 1. REPOSITORY PRÜFEN / ERSTELLEN
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}"
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            ergebnis["repository"] = True
        else:
            url_create = "https://api.github.com/user/repos"
            payload = {
                "name": repo,
                "description": "Code_Maker_Matrix (CMM) – Die ultimative lokale KI-Entwicklerzentrale",
                "private": False,
                "has_issues": True,
                "has_projects": True,
                "has_wiki": True
            }
            response = requests.post(url_create, headers=headers, json=payload, timeout=30)
            if response.status_code in (200, 201):
                ergebnis["repository"] = True
            else:
                ergebnis["fehler"].append(f"Repository-Erstellung: {response.status_code}")
    except Exception as e:
        ergebnis["fehler"].append(f"Repository-Fehler: {e}")

    # 2. DATEIEN HOCHLADEN
    dateien = [
        "dashboard.py", "key_manager.py", "github_explorer.py",
        "agent_manager.py", "batch_processor.py", "web_scraper.py",
        "skill_loader.py", "git_integration.py", "vscode_export.py",
        "project_orchestrator.py", "config.py", "code_wrangler.py",
        "zeitkapsel.py", "bruecke.py", "ai_assistant.py",
        "starte_dashboard.bat"
    ]

    for dateiname in dateien:
        pfad = config.BASE_DIR / dateiname
        if not pfad.exists():
            ergebnis["fehler"].append(f"Datei nicht gefunden: {dateiname}")
            continue

        try:
            content = pfad.read_bytes()
            encoded = base64.b64encode(content).decode()
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{dateiname}"
            payload = {
                "message": f"Add {dateiname} - CMM 8.0",
                "content": encoded,
                "branch": "main"
            }
            response = requests.put(url, headers=headers, json=payload, timeout=30)
            if response.status_code in (200, 201):
                ergebnis["dateien"].append(dateiname)
            else:
                ergebnis["fehler"].append(f"{dateiname}: {response.status_code}")
        except Exception as e:
            ergebnis["fehler"].append(f"{dateiname}: {e}")

    # 3. README.md hochladen
    readme_pfad = config.BASE_DIR / "README_CMM.md"
    if readme_pfad.exists():
        try:
            content = readme_pfad.read_bytes()
            encoded = base64.b64encode(content).decode()
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/README.md"
            payload = {
                "message": "docs: add README for CMM 8.0",
                "content": encoded,
                "branch": "main"
            }
            response = requests.put(url, headers=headers, json=payload, timeout=30)
            if response.status_code in (200, 201):
                ergebnis["dateien"].append("README.md")
            else:
                ergebnis["fehler"].append(f"README.md: {response.status_code}")
        except Exception as e:
            ergebnis["fehler"].append(f"README.md: {e}")

    # 4. RELEASE ERSTELLEN
    try:
        url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        payload = {
            "tag_name": "v8.0",
            "target_commitish": "main",
            "name": "CMM 8.0 \"The Unified Agent\"",
            "body": """# CMM 8.0 – The Unified Agent

Code_Maker_Matrix (CMM) ist eine vollständig lokale KI-Entwicklerzentrale mit:

- 🤖 KI-Assistent (Chat, Code-Generierung, Analyse, Fixing, Optimierung)
- 🤖 Agenten-Modus mit 6 Subagenten
- 🧱 Legostein-Fabrik (AST-Parser, Ampel, Graph)
- 🛠️ Toolsammlung (System, Health, Backup, Statistiken)
- 🚀 Projekt erstellen aus Ideen
- 💾 Zeitmaschine mit Backups & Sandbox
- 🔑 Enterprise-Lizenzsystem
- 🧩 CMM-Skills (YAML-Workflows)
- 📦 Git-Integration & VS Code Export
- 🧪 2-Tage-Testlizenz

## Installation

1. Repository klonen: `git clone https://github.com/GabelGold/Code_Maker_Matrix.git`
2. Abhängigkeiten installieren: `pip install -r requirements.txt`
3. Ollama starten: `ollama serve`
4. CMM starten: `starte_dashboard.bat`

## Lizenz

CMM ist lizenziert. Testversion: 2 Tage kostenlos.
Voll-Lizenz bei: c.schmitt@me.com""",
            "draft": False,
            "prerelease": False
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in (200, 201):
            ergebnis["release"] = True
        else:
            ergebnis["fehler"].append(f"Release-Erstellung: {response.status_code}")
    except Exception as e:
        ergebnis["fehler"].append(f"Release-Fehler: {e}")

    return ergebnis