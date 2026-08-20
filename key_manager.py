# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Lizenzsystem

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
from pathlib import Path
from typing import Optional

import config

SALT = "CMM_2026_Christian_Schmitt_Solingen"
LIZENZ_DATEI = config.BASE_DIR / "license.lic"


def generiere_key(name: str, email: str, ablaufdatum: str) -> str:
    daten = f"{name}|{email}|{ablaufdatum}|{SALT}"
    signatur = hashlib.sha256(daten.encode()).hexdigest()[:16]
    lizenz = {
        "name": name,
        "email": email,
        "ablaufdatum": ablaufdatum,
        "signatur": signatur,
        "erstellt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    json_str = json.dumps(lizenz, ensure_ascii=False)
    return base64.b64encode(json_str.encode()).decode()


def validiere_key(key: str) -> dict:
    ergebnis = {
        "valid": False,
        "name": "",
        "email": "",
        "ablaufdatum": "",
        "abgelaufen": False,
        "tage_uebrig": 0,
        "fehler": "",
    }
    try:
        json_str = base64.b64decode(key.encode()).decode()
        lizenz = json.loads(json_str)
        for feld in ["name", "email", "ablaufdatum", "signatur"]:
            if feld not in lizenz:
                ergebnis["fehler"] = f"Fehlendes Feld: {feld}"
                return ergebnis
        daten = f"{lizenz['name']}|{lizenz['email']}|{lizenz['ablaufdatum']}|{SALT}"
        signatur_check = hashlib.sha256(daten.encode()).hexdigest()[:16]
        if signatur_check != lizenz["signatur"]:
            ergebnis["fehler"] = "Ungültige Lizenz (Signaturfehler)"
            return ergebnis
        try:
            ablauf = datetime.datetime.strptime(lizenz["ablaufdatum"], "%Y-%m-%d")
            heute = datetime.datetime.now().date()
            abgelaufen = heute > ablauf.date()
            tage_uebrig = max(0, (ablauf.date() - heute).days)
        except ValueError:
            ergebnis["fehler"] = "Ungültiges Datumsformat (YYYY-MM-DD)"
            return ergebnis
        ergebnis["valid"] = True
        ergebnis["name"] = lizenz["name"]
        ergebnis["email"] = lizenz["email"]
        ergebnis["ablaufdatum"] = lizenz["ablaufdatum"]
        ergebnis["abgelaufen"] = abgelaufen
        ergebnis["tage_uebrig"] = 0 if abgelaufen else tage_uebrig
        if abgelaufen:
            ergebnis["fehler"] = f"Lizenz abgelaufen am {lizenz['ablaufdatum']}"
        return ergebnis
    except Exception as e:
        ergebnis["fehler"] = f"Ungültiger Key: {str(e)}"
        return ergebnis


def lizenz_speichern(key: str) -> None:
    LIZENZ_DATEI.write_text(key, encoding="utf-8")


def lizenz_laden() -> Optional[str]:
    if LIZENZ_DATEI.exists():
        return LIZENZ_DATEI.read_text(encoding="utf-8").strip()
    return None


def lizenz_loeschen() -> None:
    if LIZENZ_DATEI.exists():
        LIZENZ_DATEI.unlink()


def generiere_test_lizenz() -> str:
    """Generiert eine 2-Tage-Testlizenz für einen neuen Nutzer."""
    ablaufdatum = (datetime.datetime.now() + datetime.timedelta(days=2)).strftime("%Y-%m-%d")
    return generiere_key("Test-Nutzer", "test@cmm.local", ablaufdatum)


def ist_test_lizenz(key: str) -> bool:
    """Prüft, ob es sich um eine Testlizenz handelt."""
    ergebnis = validiere_key(key)
    if ergebnis.get("valid"):
        return ergebnis.get("email", "") == "test@cmm.local"
    return False
