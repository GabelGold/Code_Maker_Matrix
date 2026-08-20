# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – AST-basierter Code-Scanner

Analysiert Python-Dateien ohne KI. Die optionale Ein-Satz-Beschreibung
kommt von einer lokalen Ollama-Instanz; fehlt sie, bleibt der Stein
'Unbekannter Stein'. Bereits gesehene Code-Hashes werden aus dem Cache
bedient, damit Ollama nicht doppelt belastet wird.

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import config

try:
    import requests
except ImportError:  # Benötigt: pip install requests
    requests = None

CACHE_DATEI = config.BASE_DIR / ".ki_beschreibungs_cache.json"
_BUILTIN_NAMEN = set(dir(__builtins__)) if not isinstance(__builtins__, dict) else set(__builtins__)


def _cache_laden() -> dict[str, str]:
    if not CACHE_DATEI.exists():
        return {}
    try:
        daten = json.loads(CACHE_DATEI.read_text(encoding="utf-8"))
        if isinstance(daten, dict):
            return {str(k): str(v) for k, v in daten.items()}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return {}


def _cache_speichern(cache: dict[str, str]) -> None:
    try:
        CACHE_DATEI.write_text(
            json.dumps(cache, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
    except OSError:
        pass


_BESCHREIBUNGS_CACHE: dict[str, str] = _cache_laden()


def _soll_ignoriert_werden(name: str) -> bool:
    return name in config.IGNORE_LIST


def _zaehle_zeilen(knoten: ast.AST) -> int:
    ende = getattr(knoten, "end_lineno", None)
    start = getattr(knoten, "lineno", None)
    if start is None:
        return 1
    if ende is None:
        return 1
    return max(1, ende - start + 1)


def _parameter_anzahl(knoten: ast.AST) -> int:
    if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return 0
    args = knoten.args
    anzahl = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.vararg:
        anzahl += 1
    if args.kwarg:
        anzahl += 1
    erste = args.posonlyargs[0] if args.posonlyargs else (args.args[0] if args.args else None)
    if erste is not None and erste.arg in ("self", "cls") and anzahl > 0:
        anzahl -= 1
    return anzahl


def _quellausschnitt(knoten: ast.AST, quellzeilen: list[str]) -> str:
    start = max(0, (getattr(knoten, "lineno", 1) or 1) - 1)
    ende = getattr(knoten, "end_lineno", None)
    if ende is None:
        ende = start + 1
    return "\n".join(quellzeilen[start:ende])


def _zaehle_imports(baum: ast.AST) -> int:
    return sum(1 for knoten in ast.walk(baum) if isinstance(knoten, (ast.Import, ast.ImportFrom)))


def _sammle_importe(baum: ast.AST) -> dict[str, Any]:
    """Liest import / from-import und merkt sich lokale Namen plus Herkunftsmodul."""
    namen: list[str] = []
    modul_von: dict[str, str] = {}
    original_von: dict[str, str] = {}
    gesehen: set[str] = set()

    def _add(lokal: str, modul: str | None, original: str | None = None) -> None:
        if not lokal or lokal == "*" or lokal in gesehen:
            return
        gesehen.add(lokal)
        namen.append(lokal)
        if modul:
            modul_von[lokal] = modul
        original_von[lokal] = original or lokal

    for knoten in getattr(baum, "body", []):
        if isinstance(knoten, ast.Import):
            for alias in knoten.names:
                lokal = alias.asname or alias.name.split(".")[0]
                _add(lokal, alias.name, alias.name)
        elif isinstance(knoten, ast.ImportFrom):
            quellmodul = knoten.module or ""
            for alias in knoten.names:
                lokal = alias.asname or alias.name
                _add(lokal, quellmodul, alias.name)

    return {"namen": namen, "modul_von": modul_von, "original_von": original_von}


class _AufrufBesucher(ast.NodeVisitor):
    """Sammelt Funktionsaufrufe im AST, ohne den Stein selbst.

    Importierte Namen (auch aus anderen Dateien, z. B. from utils import hilfsfunktion)
    werden bevorzugt und mit Herkunftsmodul gekennzeichnet.
    """

    def __init__(self, eigener_name: str, import_info: dict[str, Any] | None = None) -> None:
        self.eigener_name = eigener_name
        self.import_namen = set((import_info or {}).get("namen") or [])
        self.modul_von = dict((import_info or {}).get("modul_von") or {})
        self.original_von = dict((import_info or {}).get("original_von") or {})
        self.importierte_aufrufe: list[str] = []
        self.andere_aufrufe: list[str] = []
        self._gesehen: set[str] = set()

    def visit_Call(self, knoten: ast.Call) -> None:
        roh, lokal, modul_alias = self._call_teile(knoten)
        if not roh:
            self.generic_visit(knoten)
            return
        if lokal == self.eigener_name and not modul_alias:
            self.generic_visit(knoten)
            return
        if lokal in _BUILTIN_NAMEN and lokal not in self.import_namen:
            self.generic_visit(knoten)
            return

        ist_import = lokal in self.import_namen or modul_alias in self.import_namen
        if ist_import:
            schluessel = modul_alias if modul_alias in self.import_namen else lokal
            herkunft = self.modul_von.get(schluessel, "")
            original = self.original_von.get(lokal, lokal)
            if herkunft and original:
                if herkunft.endswith("." + original) or herkunft == original:
                    anzeige = herkunft
                else:
                    anzeige = f"{herkunft}.{original}"
            else:
                anzeige = roh
        else:
            anzeige = roh

        if anzeige not in self._gesehen:
            self._gesehen.add(anzeige)
            if ist_import:
                self.importierte_aufrufe.append(anzeige)
            else:
                self.andere_aufrufe.append(anzeige)
        self.generic_visit(knoten)

    @staticmethod
    def _call_teile(knoten: ast.Call) -> tuple[str | None, str | None, str | None]:
        funktion = knoten.func
        if isinstance(funktion, ast.Name):
            return funktion.id, funktion.id, None
        if isinstance(funktion, ast.Attribute):
            lokal = funktion.attr
            modul_alias = None
            if isinstance(funktion.value, ast.Name):
                modul_alias = funktion.value.id
                roh = f"{modul_alias}.{lokal}"
            else:
                roh = lokal
            return roh, lokal, modul_alias
        return None, None, None


def analysiere_code(projekt_pfad: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Findet alle Funktionen und Klassen in .py-Dateien eines Projektordners.

    Nutzt os.walk und ast.parse. Keine KI. Jeder Treffer ist ein 'Legostein'
    mit Zeilenzahl, Parameterzahl, Ampel, Nachbarn, Importzahl, async-Flag
    und Docstring.
    """
    wurzel = Path(projekt_pfad)
    steine: list[dict[str, Any]] = []
    if not wurzel.exists() or not wurzel.is_dir():
        return steine

    for dirpfad, dirnamen, dateinamen in os.walk(wurzel):
        dirnamen[:] = [d for d in dirnamen if not _soll_ignoriert_werden(d)]
        for dateiname in dateinamen:
            if not dateiname.endswith(".py"):
                continue
            dateipfad = Path(dirpfad) / dateiname
            try:
                quelltext = dateipfad.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                baum = ast.parse(quelltext, filename=str(dateipfad))
            except SyntaxError:
                continue

            quellzeilen = quelltext.splitlines()
            try:
                rel_pfad = str(dateipfad.relative_to(wurzel))
            except ValueError:
                rel_pfad = str(dateipfad)

            anzahl_imports = _zaehle_imports(baum)
            import_info = _sammle_importe(baum)

            for knoten in ast.walk(baum):
                if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    zeilen = _zaehle_zeilen(knoten)
                    parameter = _parameter_anzahl(knoten)
                    koerper = _quellausschnitt(knoten, quellzeilen)
                    steine.append(
                        {
                            "typ": "funktion",
                            "name": knoten.name,
                            "datei": rel_pfad,
                            "zeilen": zeilen,
                            "parameter": parameter,
                            "ampel": berechne_ampel(zeilen, parameter),
                            "code": koerper,
                            "lineno": knoten.lineno,
                            "nachbarn": finde_nachbarn(koerper, knoten.name, import_info),
                            "anzahl_imports": anzahl_imports,
                            "ist_async": isinstance(knoten, ast.AsyncFunctionDef),
                            "docstring": ast.get_docstring(knoten) or "",
                            "import_namen": list(import_info.get("namen") or []),
                            "import_module": dict(import_info.get("modul_von") or {}),
                            "import_original": dict(import_info.get("original_von") or {}),
                        }
                    )
                elif isinstance(knoten, ast.ClassDef):
                    zeilen = _zaehle_zeilen(knoten)
                    methoden = [
                        kind.name
                        for kind in knoten.body
                        if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    koerper = _quellausschnitt(knoten, quellzeilen)
                    klassen_nachbarn = finde_nachbarn(koerper, knoten.name, import_info)
                    for methode in methoden:
                        if methode not in klassen_nachbarn and len(klassen_nachbarn) < config.MAX_NACHBARN:
                            klassen_nachbarn.append(methode)
                    steine.append(
                        {
                            "typ": "klasse",
                            "name": knoten.name,
                            "datei": rel_pfad,
                            "zeilen": zeilen,
                            "parameter": len(methoden),
                            "ampel": berechne_ampel(zeilen, len(methoden)),
                            "code": koerper,
                            "lineno": knoten.lineno,
                            "nachbarn": klassen_nachbarn[: config.MAX_NACHBARN],
                            "methoden": methoden,
                            "anzahl_imports": anzahl_imports,
                            "ist_async": False,
                            "docstring": ast.get_docstring(knoten) or "",
                            "import_namen": list(import_info.get("namen") or []),
                            "import_module": dict(import_info.get("modul_von") or {}),
                            "import_original": dict(import_info.get("original_von") or {}),
                        }
                    )

    steine.sort(key=lambda s: (s["datei"], s["lineno"], s["name"]))
    return steine


def hole_ki_beschreibung(code: str) -> str:
    """Sendet Code an Ollama und holt eine 1-Satz-Beschreibung auf Deutsch.

    Gleicher Code (SHA-256) wird aus dem Cache geliefert. Timeout aus config.
    Antwortet Ollama nicht, oder fehlt requests, wird 'Unbekannter Stein' zurückgegeben.
    """
    if not code or not str(code).strip():
        return "Unbekannter Stein"

    schluessel = hashlib.sha256(str(code).encode("utf-8", errors="replace")).hexdigest()
    if schluessel in _BESCHREIBUNGS_CACHE:
        return _BESCHREIBUNGS_CACHE[schluessel]

    if requests is None:
        return "Unbekannter Stein"

    payload = {
        "model": config.OLLAMA_MODELL,
        "prompt": (
            "Beschreibe die folgende Python-Funktion oder Klasse in genau einem "
            "deutschen Satz. Keine Einleitung, nur dieser eine Satz.\n\n"
            f"{str(code)[:4000]}"
        ),
        "stream": False,
    }
    text = "Unbekannter Stein"
    try:
        antwort = requests.post(
            config.OLLAMA_URL,
            json=payload,
            timeout=config.OLLAMA_TIMEOUT,
        )
        antwort.raise_for_status()
        daten = antwort.json()
        roh = str(daten.get("response") or "").strip()
        if roh:
            text = roh
            for trenner in (".", "!", "?"):
                if trenner in roh:
                    erster = roh.split(trenner)[0].strip()
                    if erster:
                        text = erster + trenner
                        break
            else:
                text = roh.splitlines()[0].strip()
    except Exception:
        text = "Unbekannter Stein"

    if text != "Unbekannter Stein":
        _BESCHREIBUNGS_CACHE[schluessel] = text
        _cache_speichern(_BESCHREIBUNGS_CACHE)
    return text


def berechne_ampel(zeilen: int, parameter: int) -> str:
    """Komplexitäts-Ampel für einen Legostein.

    🟢  höchstens 30 Zeilen und höchstens 5 Parameter
    🟡  31–50 Zeilen oder 6–7 Parameter
    🔴  mehr als 50 Zeilen oder mehr als 7 Parameter
    """
    zeilen = int(zeilen or 0)
    parameter = int(parameter or 0)
    if zeilen > 50 or parameter > 7:
        return "🔴"
    if zeilen > 30 or parameter > 5:
        return "🟡"
    return "🟢"


def finde_nachbarn(
    code: str,
    funktionsname: str,
    import_info: dict[str, Any] | None = None,
) -> list[str]:
    """Sucht Aufrufe anderer Funktionen im Stein-Code (höchstens MAX_NACHBARN).

    Importierte Namen (from utils import hilfsfunktion / import utils) werden
    erkannt und gegenüber lokalen Hilfsaufrufen bevorzugt.
    """
    if not code:
        return []
    try:
        baum = ast.parse(code)
    except SyntaxError:
        return []
    besucher = _AufrufBesucher(funktionsname, import_info)
    besucher.visit(baum)
    gebuendelt = besucher.importierte_aufrufe + besucher.andere_aufrufe
    return gebuendelt[: config.MAX_NACHBARN]
