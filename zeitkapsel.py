# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Zeitmaschine: Backup, Sandbox, Panik-Knopf

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import ast
import datetime
import difflib
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import config

BACKUP_INFO_NAME = "backup_info.json"


def _projektname(projekt_pfad: str | Path) -> str:
    return Path(projekt_pfad).name


def _jetzt() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _backups_fuer(projektname: str) -> list[Path]:
    if not config.ZEITMASCHINE_DIR.exists():
        return []
    treffer = [
        pfad
        for pfad in config.ZEITMASCHINE_DIR.iterdir()
        if pfad.is_dir() and pfad.name.startswith(projektname + "_")
    ]
    treffer.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return treffer


def _ignore_beim_kopieren(verzeichnis: str, inhalt: list[str]) -> list[str]:
    """Ignoriert systemrelevante Ordner beim Kopieren (Backup & Sandbox)."""
    ignore = set(config.IGNORE_LIST)
    ignore.add("ZEITMASCHINE")
    ignore.add("SANDBOX")
    ignore.add("BERICHTE")
    ignore.add("PROJEKTE")
    return [name for name in inhalt if name in ignore or name.endswith(".pyc")]


def _sicherheitscheck_quelle(quelle: Path) -> None:
    aufgeloest = quelle.resolve()
    verboten = {
        config.ZEITMASCHINE_DIR.resolve(): "Kann nicht das ZEITMASCHINE-Verzeichnis sichern!",
        config.SANDBOX_DIR.resolve(): "Kann nicht das SANDBOX-Verzeichnis sichern!",
    }
    if aufgeloest in verboten:
        raise ValueError(verboten[aufgeloest])
    try:
        aufgeloest.relative_to(config.ZEITMASCHINE_DIR.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("Kann nicht ein Verzeichnis innerhalb von ZEITMASCHINE sichern!")


def _rel_datei(quelle: Path, dateiname: str) -> Path:
    rel_datei = Path(dateiname)
    if rel_datei.is_absolute():
        try:
            rel_datei = rel_datei.relative_to(quelle)
        except ValueError:
            rel_datei = Path(rel_datei.name)
    return rel_datei


def _modulname_aus_datei(rel_datei: Path) -> str:
    teile = list(rel_datei.with_suffix("").parts)
    if not teile:
        return ""
    if teile[-1] == "__init__":
        teile = teile[:-1]
    return ".".join(teile)


def _backup_info_lesen(backup_ordner: Path) -> dict[str, Any]:
    pfad = backup_ordner / BACKUP_INFO_NAME
    if not pfad.exists():
        return {}
    try:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        return daten if isinstance(daten, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _backup_info_schreiben(backup_ordner: Path, info: dict[str, Any]) -> None:
    pfad = backup_ordner / BACKUP_INFO_NAME
    pfad.write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


def _ist_vollstaendige_datei(code: str) -> bool:
    try:
        baum = ast.parse(code)
    except SyntaxError:
        return False
    imports = sum(1 for n in baum.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    defs = sum(
        1 for n in baum.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    return (imports >= 1 and defs >= 2) or defs >= 3


def _stein_spanne(original: str, stein: dict[str, Any]) -> tuple[int, int] | None:
    try:
        baum = ast.parse(original)
    except SyntaxError:
        return None
    name = stein.get("name")
    lineno = stein.get("lineno")
    treffer = None
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if knoten.name == name and (lineno is None or knoten.lineno == lineno):
                treffer = knoten
                break
            if knoten.name == name:
                treffer = knoten
    if treffer is None or not getattr(treffer, "end_lineno", None):
        return None
    return treffer.lineno, treffer.end_lineno


def _einruecken_wie_original(original_zeile: str, neuer_code: str) -> str:
    kopf = original_zeile[: len(original_zeile) - len(original_zeile.lstrip(" \t"))]
    if not kopf:
        return neuer_code
    zeilen = neuer_code.splitlines()
    if not zeilen:
        return neuer_code
    erste = zeilen[0]
    if erste.startswith(kopf) or not erste.strip():
        return neuer_code
    return "\n".join((kopf + z if z.strip() else z) for z in zeilen)


def zieldatei_inhalt(
    original_text: str,
    geänderter_code: str,
    stein: dict[str, Any] | None = None,
) -> str:
    """Baut den neuen Dateiinhalt: ganzer File-Ersatz oder Stein-Spleiß."""
    neuer = geänderter_code.replace("\r\n", "\n")
    if not stein or _ist_vollstaendige_datei(neuer):
        return neuer if neuer.endswith("\n") else neuer + "\n"
    spanne = _stein_spanne(original_text, stein)
    if spanne is None:
        start = max(int(stein.get("lineno") or 1) - 1, 0)
        laenge = int(stein.get("zeilen") or 1)
        ende = start + max(laenge, 1)
    else:
        start = spanne[0] - 1
        ende = spanne[1]
    zeilen = original_text.splitlines(keepends=True)
    if start >= len(zeilen):
        return (original_text.rstrip() + "\n\n" + neuer).rstrip() + "\n"
    neu_block = _einruecken_wie_original(zeilen[start], neuer)
    if not neu_block.endswith("\n"):
        neu_block += "\n"
    return "".join(zeilen[:start]) + neu_block + "".join(zeilen[ende:])


def _syntax_zeile_aus_fehler(text: str) -> int | None:
    treffer = re.search(r"line (\d+)", text or "")
    if treffer:
        try:
            return int(treffer.group(1))
        except ValueError:
            return None
    return None


def _diff_zaehlen(diff_zeilen: list[str]) -> tuple[int, int]:
    hinzu = sum(1 for z in diff_zeilen if z.startswith("+") and not z.startswith("+++"))
    weg = sum(1 for z in diff_zeilen if z.startswith("-") and not z.startswith("---"))
    return hinzu, weg


def backup_erstellen(
    projekt_pfad: str | Path,
    anzahl_legosteine: int | None = None,
) -> Path:
    """Kopiert das Projekt nach ZEITMASCHINE/[Name_Zeitstempel]. Behält nur die 5 neuesten.

    Schreibt backup_info.json mit Projektname, Anzahl Legosteine und Datum.
    """
    quelle = Path(projekt_pfad)
    if not quelle.exists() or not quelle.is_dir():
        raise FileNotFoundError(f"Projektordner nicht gefunden: {quelle}")
    _sicherheitscheck_quelle(quelle)

    config.ZEITMASCHINE_DIR.mkdir(parents=True, exist_ok=True)
    stempel = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    name = _projektname(quelle)
    ziel = config.ZEITMASCHINE_DIR / f"{name}_{stempel}"
    if ziel.exists():
        shutil.rmtree(ziel, ignore_errors=True)
    shutil.copytree(quelle, ziel, ignore=_ignore_beim_kopieren)

    info = {
        "projektname": name,
        "anzahl_legosteine": int(anzahl_legosteine) if anzahl_legosteine is not None else 0,
        "datum": _jetzt(),
        "quelle": str(quelle),
    }
    _backup_info_schreiben(ziel, info)

    backups = _backups_fuer(name)
    for alt in backups[config.MAX_BACKUPS :]:
        shutil.rmtree(alt, ignore_errors=True)
    return ziel


def sandbox_testen(
    projekt_pfad: str | Path,
    geänderter_code: str,
    dateiname: str,
    stein: dict[str, Any] | None = None,
) -> dict:
    """Kopiert das Projekt in die Sandbox, prüft Syntax, Import und Diff.

    Syntax via py_compile. Import via python -c "import modul".
    Diff via difflib.unified_diff. Änderung über config.DIFF_SCHWELLE führt zum Abbruch.
    """
    quelle = Path(projekt_pfad)
    if not quelle.exists() or not quelle.is_dir():
        raise FileNotFoundError(f"Projektordner nicht gefunden: {quelle}")
    _sicherheitscheck_quelle(quelle)

    config.SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
    sandbox = config.SANDBOX_DIR / f"{quelle.name}__sandbox"
    quelle_aufgeloest = quelle.resolve()
    if sandbox.exists():
        shutil.rmtree(sandbox, ignore_errors=True)
    if sandbox.resolve() == quelle_aufgeloest:
        sandbox = config.SANDBOX_DIR / f"{quelle.name}__lauf"
        if sandbox.exists():
            shutil.rmtree(sandbox, ignore_errors=True)
    shutil.copytree(quelle, sandbox, ignore=_ignore_beim_kopieren)

    rel_datei = _rel_datei(quelle, dateiname)
    original_datei = quelle / rel_datei
    original_text = ""
    if original_datei.exists() and original_datei.is_file():
        original_text = original_datei.read_text(encoding="utf-8", errors="replace")

    neuer_inhalt = zieldatei_inhalt(original_text, geänderter_code, stein)
    ziel_datei = sandbox / rel_datei
    ziel_datei.parent.mkdir(parents=True, exist_ok=True)
    ziel_datei.write_text(neuer_inhalt, encoding="utf-8")

    syntax_ok = True
    syntax_fehler = None
    syntax_zeile = None
    try:
        py_compile.compile(str(ziel_datei), doraise=True)
    except py_compile.PyCompileError as fehler:
        syntax_ok = False
        syntax_fehler = str(fehler)
        syntax_zeile = _syntax_zeile_aus_fehler(syntax_fehler)

    if syntax_ok:
        lauf = subprocess.run(
            [sys.executable, "-m", "py_compile", str(ziel_datei)],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if lauf.returncode != 0:
            syntax_ok = False
            syntax_fehler = (lauf.stderr or lauf.stdout or "py_compile fehlgeschlagen").strip()
            syntax_zeile = _syntax_zeile_aus_fehler(syntax_fehler or "")

    import_ok = False
    import_fehler = None
    modulname = _modulname_aus_datei(rel_datei)
    if not syntax_ok:
        import_fehler = "Übersprungen, weil Syntaxprüfung fehlgeschlagen ist."
    elif not modulname or not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", modulname):
        import_fehler = f"Kein gültiger Modulname für {rel_datei.as_posix()}."
    else:
        env = os.environ.copy()
        pythonpath = str(sandbox)
        alt = env.get("PYTHONPATH")
        env["PYTHONPATH"] = pythonpath if not alt else pythonpath + os.pathsep + alt
        lauf = subprocess.run(
            [sys.executable, "-c", f"import {modulname}"],
            cwd=str(sandbox),
            capture_output=True,
            text=True,
            timeout=20,
            env=env,
        )
        if lauf.returncode == 0:
            import_ok = True
        else:
            import_fehler = (lauf.stderr or lauf.stdout or "Import fehlgeschlagen").strip()

    original_zeilen = original_text.splitlines()
    neue_zeilen = neuer_inhalt.splitlines()
    diff_zeilen = list(
        difflib.unified_diff(
            original_zeilen,
            neue_zeilen,
            fromfile="original/" + rel_datei.as_posix(),
            tofile="geaendert/" + rel_datei.as_posix(),
            lineterm="",
        )
    )
    matcher = difflib.SequenceMatcher(a=original_text, b=neuer_inhalt)
    aenderung_prozent = round((1.0 - matcher.ratio()) * 100.0, 2)
    schwelle = float(getattr(config, "DIFF_SCHWELLE", 20) or 20)
    abbruch = aenderung_prozent > schwelle
    hinzu, weg = _diff_zaehlen(diff_zeilen)

    if not syntax_ok:
        meldung = f"Syntaxfehler: {syntax_fehler}"
    elif not import_ok:
        meldung = f"Import-Test fehlgeschlagen: {import_fehler}"
    elif abbruch:
        meldung = f"Abbruch: Diff {aenderung_prozent} % übersteigt {schwelle:g} %."
    else:
        meldung = "Sandbox-Test erfolgreich."

    return {
        "syntax_ok": syntax_ok,
        "syntax_fehler": syntax_fehler,
        "syntax_zeile": syntax_zeile,
        "import_ok": import_ok,
        "import_fehler": import_fehler,
        "modulname": modulname,
        "diff": "\n".join(diff_zeilen),
        "aenderung_prozent": aenderung_prozent,
        "zeilen_hinzugefuegt": hinzu,
        "zeilen_geloescht": weg,
        "abbruch": abbruch,
        "sandbox_pfad": str(sandbox),
        "datei": str(rel_datei),
        "neuer_inhalt": neuer_inhalt,
        "zeitstempel": _jetzt(),
        "erfolg": bool(syntax_ok and import_ok and not abbruch),
        "meldung": meldung,
    }


def code_uebernehmen(
    projekt_pfad: str | Path,
    geänderter_code: str,
    dateiname: str,
    stein: dict[str, Any] | None = None,
    anzahl_legosteine: int | None = None,
) -> dict:
    """Legt zuerst ein Backup an und überschreibt dann die Original-Datei."""
    quelle = Path(projekt_pfad)
    rel_datei = _rel_datei(quelle, dateiname)
    original_datei = quelle / rel_datei
    original_text = ""
    if original_datei.exists() and original_datei.is_file():
        original_text = original_datei.read_text(encoding="utf-8", errors="replace")

    backup = backup_erstellen(quelle, anzahl_legosteine=anzahl_legosteine)
    neuer_inhalt = zieldatei_inhalt(original_text, geänderter_code, stein)
    original_datei.parent.mkdir(parents=True, exist_ok=True)
    original_datei.write_text(neuer_inhalt, encoding="utf-8")
    return {
        "erfolg": True,
        "backup": str(backup),
        "datei": str(original_datei),
        "meldung": f"Code übernommen nach {original_datei}. Backup: {backup.name}",
        "zeitstempel": _jetzt(),
    }


def panik_knopf(projekt_pfad: str | Path) -> dict:
    """Stellt das neueste Backup wieder her. Löscht den Projektordner vorher.

    Liest backup_info.json und gibt die Metadaten in der Meldung mit.
    """
    quelle = Path(projekt_pfad)
    name = _projektname(quelle)
    backups = _backups_fuer(name)
    if not backups:
        return {
            "erfolg": False,
            "meldung": f"Kein Backup für '{name}' in {config.ZEITMASCHINE_DIR} gefunden.",
            "backup": None,
            "backup_info": {},
        }

    neuestes = backups[0]
    info = _backup_info_lesen(neuestes)
    if quelle.exists():
        shutil.rmtree(quelle, ignore_errors=True)
    shutil.copytree(neuestes, quelle)
    rest_info = quelle / BACKUP_INFO_NAME
    if rest_info.exists():
        rest_info.unlink()

    meta = []
    if info.get("projektname"):
        meta.append(f"Projekt={info.get('projektname')}")
    if "anzahl_legosteine" in info:
        meta.append(f"Legosteine={info.get('anzahl_legosteine')}")
    if info.get("datum"):
        meta.append(f"Backup-Datum={info.get('datum')}")
    meta_text = ", ".join(meta) if meta else "keine Metadaten"
    return {
        "erfolg": True,
        "meldung": (
            f"Projekt '{name}' aus Backup {neuestes.name} wiederhergestellt. "
            f"backup_info.json: {meta_text}"
        ),
        "backup": str(neuestes),
        "backup_info": info,
    }


def _ordnergroesse_bytes(pfad: Path) -> int:
    gesamt = 0
    for dirpfad, dirnamen, dateinamen in os.walk(pfad):
        dirnamen[:] = [d for d in dirnamen if d not in config.IGNORE_LIST]
        for name in dateinamen:
            try:
                gesamt += (Path(dirpfad) / name).stat().st_size
            except OSError:
                continue
    return gesamt


def alle_backups() -> list[dict[str, Any]]:
    """Listet alle Backup-Ordner in ZEITMASCHINE mit Metadaten und Größe."""
    if not config.ZEITMASCHINE_DIR.exists():
        return []
    ergebnis: list[dict[str, Any]] = []
    eintraege = [p for p in config.ZEITMASCHINE_DIR.iterdir() if p.is_dir()]
    eintraege.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for pfad in eintraege:
        info = _backup_info_lesen(pfad)
        mtime = datetime.datetime.fromtimestamp(pfad.stat().st_mtime)
        name = info.get("projektname")
        if not name:
            teile = pfad.name.rsplit("_", 2)
            name = teile[0] if len(teile) >= 3 else pfad.name
        groesse = _ordnergroesse_bytes(pfad)
        ergebnis.append(
            {
                "pfad": str(pfad),
                "ordner": pfad.name,
                "projektname": name,
                "anzahl_legosteine": info.get("anzahl_legosteine", 0),
                "datum": info.get("datum") or mtime.isoformat(timespec="seconds"),
                "groesse_bytes": groesse,
                "groesse_mb": round(groesse / (1024 * 1024), 2),
                "backup_info": info,
            }
        )
    return ergebnis


def backup_loeschen(backup_pfad: str | Path) -> dict:
    pfad = Path(backup_pfad)
    if not pfad.exists():
        return {"erfolg": False, "meldung": f"Backup nicht gefunden: {pfad}"}
    try:
        pfad.resolve().relative_to(config.ZEITMASCHINE_DIR.resolve())
    except ValueError:
        return {"erfolg": False, "meldung": "Backup liegt nicht im Ordner ZEITMASCHINE."}
    shutil.rmtree(pfad, ignore_errors=True)
    return {"erfolg": True, "meldung": f"Backup gelöscht: {pfad.name}"}


def backup_wiederherstellen(
    backup_pfad: str | Path,
    projekt_pfad: str | Path | None = None,
) -> dict:
    """Stellt ein bestimmtes Backup wieder her (nicht nur das neueste)."""
    quelle_backup = Path(backup_pfad)
    if not quelle_backup.exists() or not quelle_backup.is_dir():
        return {
            "erfolg": False,
            "meldung": f"Backup nicht gefunden: {quelle_backup}",
            "backup": None,
            "backup_info": {},
        }
    info = _backup_info_lesen(quelle_backup)
    name = info.get("projektname") or quelle_backup.name.rsplit("_", 2)[0]
    if projekt_pfad:
        ziel = Path(projekt_pfad)
    elif info.get("quelle"):
        ziel = Path(str(info["quelle"]))
    else:
        ziel = config.PROJEKTE_DIR / str(name)
    if ziel.exists():
        shutil.rmtree(ziel, ignore_errors=True)
    shutil.copytree(quelle_backup, ziel)
    rest_info = ziel / BACKUP_INFO_NAME
    if rest_info.exists():
        rest_info.unlink()
    meta = []
    if info.get("projektname"):
        meta.append(f"Projekt={info.get('projektname')}")
    if "anzahl_legosteine" in info:
        meta.append(f"Legosteine={info.get('anzahl_legosteine')}")
    if info.get("datum"):
        meta.append(f"Backup-Datum={info.get('datum')}")
    meta_text = ", ".join(meta) if meta else "keine Metadaten"
    return {
        "erfolg": True,
        "meldung": (
            f"Projekt '{name}' aus Backup {quelle_backup.name} wiederhergestellt. "
            f"backup_info.json: {meta_text}"
        ),
        "backup": str(quelle_backup),
        "backup_info": info,
        "ziel": str(ziel),
    }


def bereinige_rekursive_ordner() -> dict:
    """Durchsucht ZEITMASCHINE und SANDBOX nach rekursiven Ordnern und löscht sie."""
    geloescht: list[str] = []
    fehler: list[str] = []

    def ist_rekursiv(pfad: Path, tiefe: int = 0) -> bool:
        if tiefe > 5:
            return True
        try:
            for item in pfad.iterdir():
                if item.is_dir() and item.name == pfad.name:
                    return True
                if item.is_dir() and item.name in ("ZEITMASCHINE", "SANDBOX"):
                    return True
                if item.is_dir() and ist_rekursiv(item, tiefe + 1):
                    return True
        except (PermissionError, OSError):
            pass
        return False

    for ordner in [config.ZEITMASCHINE_DIR, config.SANDBOX_DIR]:
        if not ordner.exists():
            continue
        for item in list(ordner.iterdir()):
            if item.is_dir() and ist_rekursiv(item):
                try:
                    shutil.rmtree(item, ignore_errors=True)
                    geloescht.append(str(item))
                except Exception as e:
                    fehler.append(f"{item}: {e}")

    return {"geloescht": geloescht, "fehler": fehler}
