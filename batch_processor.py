# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Batch-Processor

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import datetime
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import config
import code_wrangler
import zeitkapsel

try:
    import requests
except ImportError:
    requests = None


def _code_aus_ki(text: str) -> str:
    treffer = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", flags=re.DOTALL | re.IGNORECASE)
    if treffer:
        return treffer[0].strip()
    return (text or "").strip()


def _optimize_single(stein: dict, ziel: str, projekt_pfad: str, mit_uebernahme: bool) -> dict:
    """Optimiert einen einzelnen Stein. Übernimmt nur nach Sandbox-Erfolg."""
    if requests is None:
        return {"erfolg": False, "meldung": "requests fehlt"}
    code = stein.get("code") or ""
    if not code:
        return {"erfolg": False, "meldung": "Kein Code gefunden"}
    prompt = (
        f"Optimiere diesen Python-Code für {ziel}.\n"
        "Liefere NUR den vollständigen neuen Code in einem ```python-Block.\n\n"
        f"```python\n{code}\n```\n"
    )
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
        neuer_code = _code_aus_ki(str(antwort.json().get("response") or ""))
        if not neuer_code:
            return {"erfolg": False, "meldung": "KI lieferte keinen Code"}

        neue_zeilen = len(neuer_code.splitlines())
        neue_ampel = code_wrangler.berechne_ampel(neue_zeilen, stein.get("parameter", 0))
        sandbox = zeitkapsel.sandbox_testen(
            projekt_pfad, neuer_code, stein.get("datei", ""), stein=stein
        )
        if not sandbox.get("erfolg"):
            return {
                "erfolg": False,
                "ampel_nachher": neue_ampel,
                "meldung": sandbox.get("meldung") or "Sandbox-Test fehlgeschlagen",
            }
        if mit_uebernahme:
            zeitkapsel.code_uebernehmen(
                projekt_pfad,
                neuer_code,
                stein.get("datei", ""),
                stein=stein,
            )
        return {
            "erfolg": True,
            "ampel_nachher": neue_ampel,
            "meldung": f"Optimiert: {neue_zeilen} Zeilen, Ampel {neue_ampel}",
        }
    except Exception as e:
        return {"erfolg": False, "meldung": f"Fehler: {e}"}


def batch_optimieren(
    projekt_pfad: str,
    ziel: str = "Geschwindigkeit und Lesbarkeit",
    max_worker: int = 3,
) -> dict[str, Any]:
    """Optimiert mehrere Legosteine (rot/gelb). Ein Backup, Sandbox vor Übernahme."""
    steine = code_wrangler.analysiere_code(projekt_pfad)
    zu_optimieren = [s for s in steine if s.get("ampel") in ("🔴", "🟡")]
    if not zu_optimieren:
        return {
            "erfolg": True,
            "meldung": "Keine Steine mit Optimierungsbedarf gefunden.",
            "ergebnisse": [],
            "erfolgreich": 0,
            "fehlgeschlagen": 0,
            "projekt": projekt_pfad,
            "ziel": ziel,
            "datum": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    try:
        zeitkapsel.backup_erstellen(projekt_pfad, anzahl_legosteine=len(steine))
    except (OSError, ValueError):
        pass

    ergebnisse: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(max_worker, len(zu_optimieren))) as executor:
        futures = {
            executor.submit(_optimize_single, stein, ziel, projekt_pfad, True): stein
            for stein in zu_optimieren
        }
        timeout = float(getattr(config, "KI_TIMEOUT", 600) or 600)
        for future in as_completed(futures):
            stein = futures[future]
            try:
                ergebnis = future.result(timeout=timeout)
                ergebnisse.append(
                    {
                        "stein": stein.get("name"),
                        "datei": stein.get("datei"),
                        "ampel_vorher": stein.get("ampel"),
                        "erfolg": bool(ergebnis.get("erfolg")),
                        "ampel_nachher": ergebnis.get("ampel_nachher"),
                        "meldung": ergebnis.get("meldung", ""),
                    }
                )
            except Exception as e:
                ergebnisse.append(
                    {
                        "stein": stein.get("name"),
                        "datei": stein.get("datei"),
                        "ampel_vorher": stein.get("ampel"),
                        "erfolg": False,
                        "fehler": str(e),
                    }
                )

    return {
        "erfolg": True,
        "projekt": projekt_pfad,
        "ziel": ziel,
        "datum": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ergebnisse": ergebnisse,
        "erfolgreich": sum(1 for e in ergebnisse if e.get("erfolg")),
        "fehlgeschlagen": sum(1 for e in ergebnisse if not e.get("erfolg")),
    }
