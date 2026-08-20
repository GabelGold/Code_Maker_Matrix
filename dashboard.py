# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Streamlit-Dashboard Enterprise

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import csv
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from importlib import metadata
from pathlib import Path

import config
import code_wrangler
import zeitkapsel
import key_manager

try:
    import streamlit as st
except ImportError:  # Benötigt: pip install streamlit
    raise SystemExit(
        "streamlit fehlt. Bitte ausführen: pip install streamlit\n"
        "Danach: starte_dashboard.bat oder 'streamlit run dashboard.py'"
    )

try:
    import requests
except ImportError:  # Benötigt: pip install requests
    requests = None

try:
    import psutil
except ImportError:  # Benötigt: pip install psutil
    psutil = None

try:
    import plotly.graph_objects as go

    PLOTLY_OK = True
except ImportError:  # Benötigt: pip install plotly
    go = None
    PLOTLY_OK = False

try:
    import pandas as pd

    PANDAS_OK = True
except ImportError:  # Benötigt: pip install pandas
    pd = None
    PANDAS_OK = False

try:
    import bruecke
except Exception:
    bruecke = None

CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
NAV_START = "🏠 Startseite"
NAV_ENTDECKEN = "🔗 CMM entdecken"
NAV_KI = "🤖 KI-Assistent"
NAV_AGENT = "🤖 Agenten-Modus"
NAV_FABRIK = "🧱 Legostein-Fabrik"
NAV_TOOLS = "🛠️ Toolsammlung"
NAV_ORCHESTRATOR = "🚀 Projekt erstellen"
NAV_SETTINGS = "⚙️ Einstellungen"
NAV_OPTIONEN = [
    NAV_START,
    NAV_ENTDECKEN,
    NAV_KI,
    NAV_AGENT,
    NAV_FABRIK,
    NAV_TOOLS,
    NAV_ORCHESTRATOR,
    NAV_SETTINGS,
]
PAKET_LISTE = ["streamlit", "requests", "pyvis", "psutil", "plotly", "pandas"]


# ---------------------------------------------------------------------------
# Design
# ---------------------------------------------------------------------------

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: "IBM Plex Sans", "Segoe UI", sans-serif; }
.stApp { background-color: #1e1e1e; color: #d4d4d4; }
[data-testid="stSidebar"] {
  background-color: #252526;
  min-width: 280px !important;
  max-width: 280px !important;
  border-right: 1px solid #3e3e42;
}
[data-testid="stSidebar"] * { color: #d4d4d4; }
[data-testid="stHeader"] { background: #1e1e1e; }
.block-container { padding-top: 1.2rem; }
.dash-logo {
  font-size: 1.15rem; font-weight: 700; color: #4a9eff;
  letter-spacing: .02em; margin-bottom: .4rem;
}
.dash-card {
  background: #2d2d30; border: 1px solid #3e3e42; border-radius: 12px;
  padding: 16px 18px; box-shadow: 0 8px 24px rgba(0,0,0,.35); margin-bottom: 12px;
}
.dash-kicker { color: #4a9eff; font-size: .78rem; font-weight: 600; letter-spacing: .08em; text-transform: uppercase; }
.dash-orange { color: #ff6b35; }
.dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  margin-right: 8px; vertical-align: middle;
}
.dot-on { background: #3ddc84; box-shadow: 0 0 8px #3ddc84; }
.dot-off { background: #e74c3c; box-shadow: 0 0 8px #e74c3c; }
hr { border: none; border-top: 1px solid #3e3e42; }
[data-testid="stMetricValue"] { color: #4a9eff; }
.stButton>button {
  border-radius: 8px; border: 1px solid #3e3e42; background: #333337; color: #eee;
}
.stButton>button:hover { border-color: #4a9eff; color: #4a9eff; }
</style>
"""


def _seite_vorbereiten() -> None:
    st.set_page_config(
        page_title="CMM 8.0 – GitHub & Testlizenz",
        page_icon="🧱",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(CSS, unsafe_allow_html=True)
    config.BERICHTE_DIR.mkdir(parents=True, exist_ok=True)
    if "dash_nav" not in st.session_state:
        st.session_state.dash_nav = NAV_START
    if "dash_nav_target" not in st.session_state:
        st.session_state.dash_nav_target = ""
    if "backup_loesch_frage" not in st.session_state:
        st.session_state.backup_loesch_frage = ""
    if "backup_restore_frage" not in st.session_state:
        st.session_state.backup_restore_frage = ""
    if "cmm_reset_frage" not in st.session_state:
        st.session_state.cmm_reset_frage = False
    for schluessel, wert in {
        "geladenes_projekt": "",
        "legosteine": [],
        "ampel_stats": {"rot": 0, "gelb": 0, "gruen": 0},
        "dateibaum": "",
        "beschreibungen": {},
        "grok_prompt": "",
    }.items():
        if schluessel not in st.session_state:
            st.session_state[schluessel] = wert
    # Ziel VOR dem Radio-Widget anwenden – sonst: StreamlitAPIException
    ziel = st.session_state.get("dash_nav_target") or ""
    if ziel:
        st.session_state.dash_nav = ziel
        st.session_state.dash_nav_target = ""
    if not st.session_state.get("_cmm_cleanup_done"):
        zeitkapsel.bereinige_rekursive_ordner()
        st.session_state._cmm_cleanup_done = True


def _karte(titel: str, kicker: str = "") -> None:
    kicker_html = f'<div class="dash-kicker">{kicker}</div>' if kicker else ""
    st.markdown(
        f'<div class="dash-card">{kicker_html}<h3 style="margin:4px 0 8px 0;color:#fff;">{titel}</h3>',
        unsafe_allow_html=True,
    )


def _karte_ende() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def _stempel() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _jetzt_lesbar() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _paket_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "nicht installiert"


def _fehlende_lib(name: str) -> None:
    st.warning(f"{name} fehlt. Funktion eingeschränkt. Bitte: `pip install {name}`")


def _nav_setzen(ziel: str) -> None:
    """Navigation merken. Wird vor dem Radio in _seite_vorbereiten übernommen."""
    st.session_state.dash_nav_target = ziel


def _lizenz_status() -> dict:
    gespeicherter_key = key_manager.lizenz_laden()
    if not gespeicherter_key:
        return {
            "ok": False,
            "grund": "fehlt",
            "fehler": "Keine gültige Lizenz gefunden.",
            "name": "",
            "ablaufdatum": "",
            "email": "",
            "test": False,
            "tage_uebrig": 0,
        }
    ergebnis = key_manager.validiere_key(gespeicherter_key)
    if not ergebnis.get("valid"):
        return {
            "ok": False,
            "grund": "ungueltig",
            "fehler": ergebnis.get("fehler") or "Ungültiger Lizenz-Key.",
            "name": "",
            "ablaufdatum": "",
            "email": "",
            "test": False,
            "tage_uebrig": 0,
        }
    if ergebnis.get("abgelaufen"):
        return {
            "ok": False,
            "grund": "abgelaufen",
            "fehler": ergebnis.get("fehler") or f"Lizenz abgelaufen am {ergebnis.get('ablaufdatum')}.",
            "name": ergebnis.get("name") or "",
            "ablaufdatum": ergebnis.get("ablaufdatum") or "",
            "email": ergebnis.get("email") or "",
            "test": key_manager.ist_test_lizenz(gespeicherter_key),
            "tage_uebrig": 0,
        }
    return {
        "ok": True,
        "grund": "ok",
        "fehler": "",
        "name": ergebnis.get("name") or "",
        "ablaufdatum": ergebnis.get("ablaufdatum") or "",
        "email": ergebnis.get("email") or "",
        "test": key_manager.ist_test_lizenz(gespeicherter_key),
        "tage_uebrig": int(ergebnis.get("tage_uebrig") or 0),
    }


def _lizenz_pruefen() -> bool:
    """Prüft, ob eine gültige Lizenz vorhanden ist (inkl. Testlizenz)."""
    gespeicherter_key = key_manager.lizenz_laden()

    if not gespeicherter_key:
        st.warning(
            "🧪 **Keine Lizenz gefunden – Testphase starten!**\n\n"
            "Du kannst CMM **2 Tage lang kostenlos testen**.\n\n"
            'Klicke auf **"Testlizenz starten"**, um sofort loszulegen.'
        )
        if st.button("🚀 Testlizenz starten (2 Tage)", key="test_lizenz_start"):
            test_key = key_manager.generiere_test_lizenz()
            key_manager.lizenz_speichern(test_key)
            st.success("✅ Testlizenz aktiviert! Seite wird neu geladen...")
            st.rerun()
        return False

    ergebnis = key_manager.validiere_key(gespeicherter_key)

    if not ergebnis.get("valid"):
        st.error(f"❌ Ungültiger Lizenz-Key! Fehler: {ergebnis.get('fehler', 'Unbekannt')}")
        if st.button("🔄 Lizenz zurücksetzen", key="lizenz_reset_ungueltig"):
            key_manager.lizenz_loeschen()
            st.rerun()
        return False

    if ergebnis.get("abgelaufen", False):
        st.error(
            "⏰ **Lizenz abgelaufen!**\n\n"
            f"**Lizenziert für:** {ergebnis.get('name', 'Unbekannt')}  \n"
            f"**Abgelaufen am:** {ergebnis.get('ablaufdatum', 'Unbekannt')}\n\n"
            "Bitte kontaktiere **Christian Schmitt**, um eine neue Lizenz zu erhalten:  \n"
            "📧 c.schmitt@me.com  \n"
            "📞 015204006286\n\n"
            "Nach dem Erhalt eines neuen Keys kannst du ihn unten eingeben."
        )
        return False

    if key_manager.ist_test_lizenz(gespeicherter_key):
        tage_uebrig = ergebnis.get("tage_uebrig", 0)
        st.info(
            f"🧪 **Testlizenz aktiv – noch {tage_uebrig} Tag(e)**\n\n"
            f"**Lizenziert für:** {ergebnis.get('name', 'Test-Nutzer')}  \n"
            f"**Gültig bis:** {ergebnis.get('ablaufdatum', 'Unbekannt')}\n\n"
            "Nach Ablauf kontaktiere bitte **Christian Schmitt**:  \n"
            "📧 c.schmitt@me.com"
        )
    else:
        st.success(
            "✅ **Lizenz gültig**  \n"
            f"**Lizenziert für:** {ergebnis.get('name', 'Unbekannt')}  \n"
            f"**Gültig bis:** {ergebnis.get('ablaufdatum', 'Unbekannt')}"
        )
    return True


def _seite_lizenz_eingabe() -> None:
    """Zeigt nur die Lizenz-Eingabeseite."""
    st.markdown("## 🔑 Code_Maker_Matrix (CMM) – Lizenz")
    st.markdown("Bitte gib deinen Lizenz-Key ein, um das Tool zu nutzen.")
    st.caption("(c) 2026 Christian Schmitt, Solingen, Germany · c.schmitt@me.com")
    key = st.text_input("Lizenz-Key", type="password", key="cmm_lizenz_start")
    if st.button("Lizenz speichern", key="cmm_lizenz_start_save"):
        if key.strip():
            ergebnis = key_manager.validiere_key(key.strip())
            if ergebnis["valid"] and not ergebnis.get("abgelaufen", False):
                key_manager.lizenz_speichern(key.strip())
                st.success("✅ Lizenz gespeichert! Bitte Seite neu laden.")
                st.rerun()
            else:
                st.error(f"❌ {ergebnis.get('fehler', 'Ungültiger Key')}")
        else:
            st.warning("Bitte einen Key eingeben.")


def _cmm_reset_system() -> None:
    """Setzt das gesamte CMM-System auf Werkseinstellungen zurück. Projekte bleiben."""
    for datei in [
        "CHAT_HISTORIE.json",
        "PROMPT_HISTORIE.json",
        ".ki_beschreibungs_cache.json",
        "settings.json",
    ]:
        pfad = config.BASE_DIR / datei
        if pfad.exists():
            try:
                pfad.unlink()
            except OSError:
                pass

    for ordner in [config.ZEITMASCHINE_DIR, config.SANDBOX_DIR, config.BERICHTE_DIR]:
        if not ordner.exists():
            continue
        for item in list(ordner.iterdir()):
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink()
            except Exception:
                pass

    for schluessel in list(st.session_state.keys()):
        if schluessel not in ("dash_nav", "dash_nav_target"):
            del st.session_state[schluessel]


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

def _ollama_host() -> str:
    return (getattr(config, "OLLAMA_HOST", None) or "http://localhost:11434").rstrip("/")


def _ollama_bin() -> str | None:
    return shutil.which("ollama")


def ollama_status() -> str:
    if requests is None:
        return "stopped"
    try:
        antwort = requests.get(_ollama_host() + "/api/tags", timeout=1.6)
        if antwort.ok:
            return "running"
    except Exception:
        pass
    return "stopped"


def ollama_starten() -> str:
    if ollama_status() == "running":
        return "Ollama läuft bereits."
    binary = _ollama_bin()
    if not binary:
        return "ollama wurde nicht im PATH gefunden. Bitte Ollama installieren."
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    try:
        proc = subprocess.Popen([binary, "serve"], **kwargs)
        (config.BASE_DIR / ".ollama_serve.pid").write_text(str(proc.pid), encoding="utf-8")
        return f"Ollama-Start ausgelöst (PID {proc.pid})."
    except OSError as fehler:
        return f"Ollama konnte nicht gestartet werden: {fehler}"


def ollama_stoppen() -> str:
    getroffen = 0
    pid_datei = config.BASE_DIR / ".ollama_serve.pid"
    if pid_datei.exists():
        try:
            pid = int(pid_datei.read_text(encoding="utf-8").strip())
            if psutil:
                try:
                    psutil.Process(pid).terminate()
                    getroffen += 1
                except Exception:
                    pass
            elif os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )
                getroffen += 1
        except ValueError:
            pass
        try:
            pid_datei.unlink()
        except OSError:
            pass

    if psutil:
        for proc in psutil.process_iter(["name", "pid"]):
            name = (proc.info.get("name") or "").lower()
            if name.startswith("ollama"):
                try:
                    proc.terminate()
                    getroffen += 1
                except Exception:
                    try:
                        proc.kill()
                        getroffen += 1
                    except Exception:
                        pass
    elif os.name == "nt":
        for exe in ("ollama.exe", "Ollama.exe"):
            lauf = subprocess.run(
                ["taskkill", "/IM", exe, "/F"],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
            )
            if lauf.returncode == 0:
                getroffen += 1

    if getroffen:
        return "Ollama-Prozess(e) beendet."
    return "Kein laufender Ollama-Prozess gefunden."


def modelle_holen() -> list[str]:
    namen: list[str] = []
    if requests is not None:
        try:
            antwort = requests.get(_ollama_host() + "/api/tags", timeout=2.5)
            if antwort.ok:
                for modell in antwort.json().get("models") or []:
                    name = modell.get("name") or modell.get("model")
                    if name:
                        namen.append(str(name))
        except Exception:
            pass
    if namen:
        return sorted(set(namen))
    binary = _ollama_bin()
    if not binary:
        return []
    try:
        lauf = subprocess.run(
            [binary, "list"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        for zeile in (lauf.stdout or "").splitlines()[1:]:
            teile = zeile.split()
            if teile:
                namen.append(teile[0])
    except Exception:
        return []
    return sorted(set(namen))


# ---------------------------------------------------------------------------
# Exporte
# ---------------------------------------------------------------------------

def _pdf_schreiben(pfad: Path, titel: str, zeilen: list[str]) -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas as pdf_canvas

        c = pdf_canvas.Canvas(str(pfad), pagesize=A4)
        breite, hoehe = A4
        y = hoehe - 48
        c.setFont("Helvetica-Bold", 14)
        c.drawString(48, y, titel.encode("latin-1", "replace").decode("latin-1"))
        y -= 28
        c.setFont("Helvetica", 9)
        for roh in zeilen:
            text = (
                roh.replace("ä", "ae")
                .replace("ö", "oe")
                .replace("ü", "ue")
                .replace("Ä", "Ae")
                .replace("Ö", "Oe")
                .replace("Ü", "Ue")
                .replace("ß", "ss")
            )
            text = text.encode("latin-1", "replace").decode("latin-1")[:110]
            if y < 40:
                c.showPage()
                y = hoehe - 48
                c.setFont("Helvetica", 9)
            c.drawString(48, y, text)
            y -= 12
        c.save()
        return str(pfad)
    except ImportError:
        pass

    def _sauber(text: str) -> str:
        t = (
            text.replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("Ä", "Ae")
            .replace("Ö", "Oe")
            .replace("Ü", "Ue")
            .replace("ß", "ss")
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        return t.encode("latin-1", "replace").decode("latin-1")[:110]

    befehle = ["BT /F1 14 Tf 48 800 Td (" + _sauber(titel) + ") Tj ET"]
    y = 780
    for roh in zeilen[:70]:
        befehle.append(f"BT /F1 9 Tf 48 {y} Td ({_sauber(roh)}) Tj ET")
        y -= 12
        if y < 40:
            break
    stream = "\n".join(befehle)
    objekte = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj",
        f"4 0 obj << /Length {len(stream.encode('latin-1'))} >> stream\n{stream}\nendstream endobj",
        "5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
    ]
    pdf = ["%PDF-1.4"]
    offsets = [0]
    cursor = 9
    for obj in objekte:
        offsets.append(cursor)
        pdf.append(obj)
        cursor += len(obj.encode("latin-1")) + 1
    xref_pos = cursor
    xref = ["xref", f"0 {len(objekte)+1}", "0000000000 65535 f "]
    for off in offsets[1:]:
        xref.append(f"{off:010d} 00000 n ")
    pdf.extend(xref)
    pdf.append(f"trailer << /Size {len(objekte)+1} /Root 1 0 R >>")
    pdf.append(f"startxref\n{xref_pos}\n%%EOF")
    pfad.write_bytes("\n".join(pdf).encode("latin-1", "replace"))
    return str(pfad)


# ---------------------------------------------------------------------------
# Seitenleiste
# ---------------------------------------------------------------------------

def _seitenleiste() -> str:
    with st.sidebar:
        st.markdown('<div class="dash-logo">🧱 Code_Maker_Matrix</div>', unsafe_allow_html=True)
        st.caption("CMM 8.0 · GitHub · Testlizenz")
        status = ollama_status()
        if status == "running":
            st.markdown(
                '<span class="dot dot-on"></span> <b>Ollama läuft</b>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<span class="dot dot-off"></span> <b>Ollama gestoppt</b>',
                unsafe_allow_html=True,
            )
        st.markdown("---")
        modelle = modelle_holen() if status == "running" else []
        if modelle:
            aktuell = config.OLLAMA_MODELL
            optionen = modelle if aktuell in modelle else [aktuell] + modelle
            try:
                index = optionen.index(aktuell) if aktuell in optionen else 0
            except ValueError:
                index = 0
            wahl = st.selectbox("Modell", optionen, index=index, key="dash_modell")
            config.OLLAMA_MODELL = wahl
        else:
            st.caption("Keine Modelle – Ollama starten, dann aktualisieren.")

        st.markdown("**Ollama-Steuerung**")
        b1, b2 = st.columns(2)
        with b1:
            if st.button("▶️ Start", key="dash_ollama_on", use_container_width=True):
                st.session_state.dash_ollama_msg = ollama_starten()
                st.rerun()
        with b2:
            if st.button("⏹️ Stopp", key="dash_ollama_off", use_container_width=True):
                st.session_state.dash_ollama_msg = ollama_stoppen()
                st.rerun()
        if st.button("🔄 Modelle aktualisieren", key="dash_modelle_reload", use_container_width=True):
            st.session_state.dash_ollama_msg = (
                f"{len(modelle_holen())} Modell(e) gelesen."
                if ollama_status() == "running"
                else "Ollama antwortet nicht."
            )
            st.rerun()
        if st.session_state.get("dash_ollama_msg"):
            st.caption(st.session_state.dash_ollama_msg)

        st.markdown("---")
        st.markdown("**Navigation**")
        st.radio(
            "Navigation",
            NAV_OPTIONEN,
            key="dash_nav",
            label_visibility="collapsed",
        )
        st.markdown("---")
        st.markdown("**🔧 System**")
        if st.button("🔄 CMM zurücksetzen", key="cmm_reset", use_container_width=True):
            st.session_state.cmm_reset_frage = True
        if st.session_state.get("cmm_reset_frage", False):
            st.warning("⚠️ DAS LÖSCHT ALLE BACKUPS, PROMPTS, CHATS UND BERICHTE!")
            st.warning("Deine Projekte in /PROJEKTE bleiben erhalten.")
            st.caption("Diese Aktion kann NICHT rückgängig gemacht werden!")
            ja, nein = st.columns(2)
            with ja:
                if st.button("✅ Ja, zurücksetzen", key="cmm_reset_yes", use_container_width=True):
                    st.session_state.cmm_reset_frage = False
                    _cmm_reset_system()
                    st.rerun()
            with nein:
                if st.button("❌ Nein, abbrechen", key="cmm_reset_no", use_container_width=True):
                    st.session_state.cmm_reset_frage = False
                    st.rerun()
        st.caption("(c) 2026 Christian Schmitt")
    return st.session_state.dash_nav


# ---------------------------------------------------------------------------
# Startseite
# ---------------------------------------------------------------------------

def _projekte() -> list[str]:
    if not config.PROJEKTE_DIR.exists():
        return []
    return sorted(
        p.name
        for p in config.PROJEKTE_DIR.iterdir()
        if p.is_dir() and p.name not in config.IGNORE_LIST
    )


def _seite_start() -> None:
    st.markdown("## 🏠 Willkommen bei Code_Maker_Matrix (CMM)")
    st.caption("Lokale KI-Entwicklerzentrale · Ollama · Legostein-Fabrik · Zeitmaschine")
    liz = _lizenz_status()
    if liz.get("ok") and liz.get("test"):
        st.info(
            f"🧪 Testlizenz aktiv – noch {liz.get('tage_uebrig', 0)} Tag(e), "
            f"gültig bis {liz.get('ablaufdatum')}. Voll-Lizenz: c.schmitt@me.com"
        )
    c1, c2, c3, c4 = st.columns(4)
    status = ollama_status()
    with c1:
        st.metric("Ollama", "🟢 läuft" if status == "running" else "🔴 gestoppt")
    with c2:
        st.metric("Projekte", str(len(_projekte())))
    with c3:
        st.metric("Backups", str(len(zeitkapsel.alle_backups())))
    with c4:
        st.metric("Python", ".".join(platform.python_version_tuple()[:2]))

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("**Statusübersicht**")
            st.write(f"Arbeitsverzeichnis: `{config.BASE_DIR}`")
            st.write(f"Ollama-Host: `{_ollama_host()}`")
            st.write(f"Aktives Modell: `{config.OLLAMA_MODELL}`")
            st.write(f"Max. Backups: {config.MAX_BACKUPS} · Nachbarn: {config.MAX_NACHBARN} · Diff-Schwelle: {config.DIFF_SCHWELLE} %")
            st.write(f"Prompts in Historie: {len(config.historie_laden())}")
    with col_b:
        with st.container(border=True):
            st.markdown("**Systeminfos**")
            st.write(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
            st.write(f"CPU: {platform.processor() or 'unbekannt'} · Kerne: {os.cpu_count() or '?'}")
            try:
                usage = shutil.disk_usage(str(config.BASE_DIR.drive) + "\\")
                frei = usage.free / (1024 ** 3)
                gesamt = usage.total / (1024 ** 3)
                st.write(f"Laufwerk {config.BASE_DIR.drive}: {frei:.1f} GB frei von {gesamt:.1f} GB")
            except OSError:
                st.write("Speicherplatz: nicht lesbar")
            if psutil:
                ram = psutil.virtual_memory()
                st.write(f"RAM: {ram.used/1024**3:.1f} / {ram.total/1024**3:.1f} GB ({ram.percent} %)")
            else:
                st.caption("RAM-Details: pip install psutil")

    st.markdown("#### Schnellstart")
    q1, q2, q3, q4 = st.columns(4)
    with q1:
        if st.button("CMM entdecken", key="dash_goto_entdecken", use_container_width=True):
            _nav_setzen(NAV_ENTDECKEN)
            st.rerun()
    with q2:
        if st.button("Zum KI-Assistenten", key="dash_goto_ki", use_container_width=True):
            _nav_setzen(NAV_KI)
            st.rerun()
    with q3:
        if st.button("Zur Fabrik", key="dash_goto_fabrik", use_container_width=True):
            _nav_setzen(NAV_FABRIK)
            st.rerun()
    with q4:
        if st.button("Zur Toolsammlung", key="dash_goto_tools", use_container_width=True):
            _nav_setzen(NAV_TOOLS)
            st.rerun()
    r1, r2, r3 = st.columns(3)
    with r1:
        if st.button("Zum Agenten-Modus", key="dash_goto_agent", use_container_width=True):
            _nav_setzen(NAV_AGENT)
            st.rerun()
    with r2:
        if st.button("Projekt erstellen", key="dash_goto_orch", use_container_width=True):
            _nav_setzen(NAV_ORCHESTRATOR)
            st.rerun()
    with r3:
        if st.button("Zu den Einstellungen", key="dash_goto_set", use_container_width=True):
            _nav_setzen(NAV_SETTINGS)
            st.rerun()


def _seite_entdecken() -> None:
    """🔗 CMM entdecken – Präsentation aus GitHub."""
    import github_explorer

    st.markdown("## 🔗 CMM entdecken")
    st.caption("Lerne Code_Maker_Matrix (CMM) kennen – direkt aus dem GitHub-Repository.")
    with st.container(border=True):
        st.markdown("### 📖 README")
        readme = github_explorer.get_readme()
        if readme and not str(readme).startswith("README.md konnte nicht"):
            st.markdown(readme)
        else:
            st.info("README.md konnte nicht geladen werden. Besuche das Repository direkt:")
            st.markdown(
                f"[GitHub-Repository](https://github.com/{github_explorer.GITHUB_OWNER}/{github_explorer.GITHUB_REPO})"
            )
    with st.container(border=True):
        st.markdown("### 📂 Repository-Struktur")
        items = github_explorer.get_repo_structure()
        if items:
            for item in items:
                if item.get("typ") == "folder":
                    st.markdown(f"📁 **{item.get('name')}**")
                else:
                    st.markdown(f"📄 `{item.get('name')}`")
        else:
            st.caption("Keine Struktur geladen.")
    with st.container(border=True):
        st.markdown("### 🔑 Lizenz & Kontakt")
        st.markdown(
            "**Code_Maker_Matrix (CMM)** ist ein lizenziertes Produkt.\n\n"
            "- 🧪 **Testlizenz:** 2 Tage kostenlos testen\n"
            "- 📧 **Voll-Lizenz:** Anfrage per E-Mail an **c.schmitt@me.com**\n"
            "- 📞 **Telefon:** 015204006286\n\n"
            "**© 2026 Christian Schmitt, Solingen, Germany**"
        )


# ---------------------------------------------------------------------------
# KI-Assistent
# ---------------------------------------------------------------------------

def _seite_ki() -> None:
    """🤖 KI-Assistent – lokaler Chat mit Ollama."""
    import ai_assistant

    st.markdown("## 🤖 Lokaler KI-Assistent")
    st.caption("Fragen stellen, Code generieren, analysieren, optimieren – alles lokal mit Ollama.")

    modelle = modelle_holen()
    aktuell = config.OLLAMA_MODELL
    if modelle:
        optionen = modelle if aktuell in modelle else [aktuell] + modelle
        index = optionen.index(aktuell) if aktuell in optionen else 0
        modell = st.selectbox("Modell", optionen, index=index, key="ki_modell")
    else:
        modell = aktuell
        st.warning("Keine Modelle gefunden. Starte Ollama in der Sidebar.")

    actions = st.tabs(
        [
            "💬 Chat",
            "📝 Code generieren",
            "🔍 Code analysieren",
            "🔧 Code fixen",
            "⚡ Code optimieren",
            "📖 Code erklären",
            "🔄 Code umwandeln",
            "📁 Projekt fragen",
            "🌐 Doku abrufen",
        ]
    )

    with actions[0]:
        st.markdown("### 💬 Chat mit der KI")
        st.caption("Stelle Fragen zu Code, Programmierung oder Projekten.")
        chat_eintraege = ai_assistant.chat_historie_laden()
        if chat_eintraege:
            for eintrag in reversed(chat_eintraege[:20]):
                rolle = eintrag.get("rolle")
                inhalt = str(eintrag.get("inhalt") or "")
                if hasattr(st, "chat_message"):
                    avatar = "🧑" if rolle == "user" else "🤖"
                    with st.chat_message("user" if rolle == "user" else "assistant", avatar=avatar):
                        st.markdown(inhalt)
                        st.caption(str(eintrag.get("datum") or ""))
                else:
                    if rolle == "user":
                        st.markdown(f"**🧑 Du:** {inhalt}")
                    else:
                        st.markdown(f"**🤖 KI:** {inhalt}")
                    st.caption(f"_{eintrag.get('datum', '')}_")
                    st.markdown("---")
        else:
            st.info("Noch keine Chat-Historie.")

        frage = st.text_area("Deine Frage", height=120, key="ki_chat_frage")
        if st.button("Absenden", type="primary", key="ki_chat_senden"):
            if frage.strip():
                ai_assistant.chat_eintrag_hinzufuegen("user", frage)
                with st.spinner(f"KI denkt nach (Timeout: {config.KI_TIMEOUT}s)..."):
                    antwort = ai_assistant.frage_an_ki(frage, modell=modell)
                ai_assistant.chat_eintrag_hinzufuegen("assistant", antwort, {"modell": modell})
                st.rerun()
            else:
                st.warning("Bitte eine Frage eingeben.")
        if st.button("Historie löschen", key="ki_chat_clear"):
            ai_assistant.chat_historie_loeschen()
            st.rerun()

    with actions[1]:
        st.markdown("### 📝 Code generieren")
        beschreibung = st.text_area(
            "Was soll der Code tun?",
            height=150,
            key="ki_gen_beschreibung",
            placeholder="z.B. Eine Funktion, die alle Dateien in einem Ordner listet",
        )
        sprache = st.selectbox(
            "Sprache",
            ["Python", "JavaScript", "TypeScript", "Java", "C#", "Go", "Rust"],
            key="ki_gen_sprache",
        )
        kontext = st.text_area(
            "Kontext (optional)",
            height=80,
            key="ki_gen_kontext",
            placeholder="z.B. Vorhandene Code-Struktur",
        )
        if st.button("Code generieren", type="primary", key="ki_gen_go"):
            if beschreibung.strip():
                with st.spinner(f"Generiere Code (Timeout: {config.KI_TIMEOUT}s)..."):
                    st.session_state.ki_gen_antwort = ai_assistant.code_generieren(
                        beschreibung, sprache, kontext, modell
                    )
            else:
                st.warning("Bitte eine Beschreibung eingeben.")
        if st.session_state.get("ki_gen_antwort"):
            st.code(st.session_state.ki_gen_antwort, language=sprache.lower())
            st.download_button(
                "Download",
                data=st.session_state.ki_gen_antwort,
                file_name=f"generated.{sprache.lower()}",
                key="ki_gen_dl",
            )

    with actions[2]:
        st.markdown("### 🔍 Code analysieren")
        code = st.text_area("Code einfügen", height=200, key="ki_ana_code")
        frage_code = st.text_input(
            "Frage zum Code",
            value="Was macht dieser Code? Gibt es Probleme?",
            key="ki_ana_frage",
        )
        if st.button("Analysieren", type="primary", key="ki_ana_go"):
            if code.strip():
                with st.spinner(f"Analysiere Code (Timeout: {config.KI_TIMEOUT}s)..."):
                    st.session_state.ki_ana_antwort = ai_assistant.code_analysieren(
                        code, frage_code, modell
                    )
            else:
                st.warning("Bitte Code einfügen.")
        if st.session_state.get("ki_ana_antwort"):
            st.markdown(st.session_state.ki_ana_antwort)

    with actions[3]:
        st.markdown("### 🔧 Code fixen")
        code = st.text_area("Code mit Fehler", height=200, key="ki_fix_code")
        problem = st.text_input("Was ist das Problem?", key="ki_fix_problem")
        if st.button("Fixen", type="primary", key="ki_fix_go"):
            if code.strip() and problem.strip():
                with st.spinner(f"Behebe Fehler (Timeout: {config.KI_TIMEOUT}s)..."):
                    st.session_state.ki_fix_antwort = ai_assistant.code_fixen(
                        code, problem, modell
                    )
            else:
                st.warning("Bitte Code und Problem angeben.")
        if st.session_state.get("ki_fix_antwort"):
            st.code(st.session_state.ki_fix_antwort, language="python")
            st.download_button(
                "Download Fix",
                data=st.session_state.ki_fix_antwort,
                file_name="fixed.py",
                key="ki_fix_dl",
            )

    with actions[4]:
        st.markdown("### ⚡ Code optimieren")
        code = st.text_area("Code einfügen", height=200, key="ki_opt_code")
        ziel = st.selectbox(
            "Optimierungsziel",
            [
                "Geschwindigkeit und Lesbarkeit",
                "Nur Geschwindigkeit",
                "Nur Lesbarkeit",
                "Speichernutzung",
            ],
            key="ki_opt_ziel",
        )
        if st.button("Optimieren", type="primary", key="ki_opt_go"):
            if code.strip():
                with st.spinner(f"Optimiere Code (Timeout: {config.KI_TIMEOUT}s)..."):
                    st.session_state.ki_opt_antwort = ai_assistant.code_optimieren(
                        code, ziel, modell
                    )
            else:
                st.warning("Bitte Code einfügen.")
        if st.session_state.get("ki_opt_antwort"):
            st.markdown(st.session_state.ki_opt_antwort)
            st.download_button(
                "Download Optimiert",
                data=st.session_state.ki_opt_antwort,
                file_name="optimized.py",
                key="ki_opt_dl",
            )

    with actions[5]:
        st.markdown("### 📖 Code erklären")
        code = st.text_area("Code einfügen", height=200, key="ki_erk_code")
        zielgruppe = st.selectbox(
            "Zielgruppe",
            ["Anfänger", "Fortgeschrittene", "Experten", "Nicht-Programmierer"],
            key="ki_erk_ziel",
        )
        if st.button("Erklären", type="primary", key="ki_erk_go"):
            if code.strip():
                with st.spinner(f"Erkläre Code (Timeout: {config.KI_TIMEOUT}s)..."):
                    st.session_state.ki_erk_antwort = ai_assistant.code_erklären(
                        code, zielgruppe, modell
                    )
            else:
                st.warning("Bitte Code einfügen.")
        if st.session_state.get("ki_erk_antwort"):
            st.markdown(st.session_state.ki_erk_antwort)

    with actions[6]:
        st.markdown("### 🔄 Code umwandeln")
        code = st.text_area("Python-Code", height=200, key="ki_um_code")
        zielsprache = st.selectbox(
            "Zielsprache",
            ["JavaScript", "TypeScript", "Java", "C#", "Go", "Rust"],
            key="ki_um_sprache",
        )
        if st.button("Umwandeln", type="primary", key="ki_um_go"):
            if code.strip():
                with st.spinner(f"Wandle Code um (Timeout: {config.KI_TIMEOUT}s)..."):
                    st.session_state.ki_um_antwort = ai_assistant.code_umwandeln(
                        code, zielsprache, modell
                    )
            else:
                st.warning("Bitte Code einfügen.")
        if st.session_state.get("ki_um_antwort"):
            st.code(st.session_state.ki_um_antwort, language=zielsprache.lower())
            st.download_button(
                "Download",
                data=st.session_state.ki_um_antwort,
                file_name=f"converted.{zielsprache.lower()}",
                key="ki_um_dl",
            )

    with actions[7]:
        st.markdown("### 📁 Projekt fragen")
        projekte = _projekte()
        if projekte:
            projekt = st.selectbox("Projekt", projekte, key="ki_proj_auswahl")
            frage_proj = st.text_area("Frage zum Projekt", height=120, key="ki_proj_frage")
            if st.button("Fragen", type="primary", key="ki_proj_go"):
                if frage_proj.strip():
                    with st.spinner(f"Analysiere Projekt (Timeout: {config.KI_TIMEOUT}s)..."):
                        pfad = str(config.PROJEKTE_DIR / projekt)
                        st.session_state.ki_proj_antwort = ai_assistant.projekt_frage(
                            frage_proj, pfad, modell
                        )
                else:
                    st.warning("Bitte eine Frage eingeben.")
            if st.session_state.get("ki_proj_antwort"):
                st.markdown(st.session_state.ki_proj_antwort)
        else:
            st.info("Keine Projekte gefunden. Lege eines in der Fabrik an.")

    with actions[8]:
        st.markdown("### 🌐 Doku abrufen")
        import web_scraper

        url = st.text_input("URL", key="ki_web_url", placeholder="https://docs.python.org/3/library/ast.html")
        if st.button("Seite laden", key="ki_web_go"):
            if url.strip():
                with st.spinner("Lade Webseite..."):
                    st.session_state.ki_web_seite = web_scraper.scrape_webseite(url.strip())
            else:
                st.warning("Bitte eine URL eingeben.")
        seite = st.session_state.get("ki_web_seite")
        if seite:
            if seite.get("erfolg"):
                st.success(f"{seite.get('titel')} · {seite.get('laenge')} Zeichen")
                st.text_area("Extrahierter Text", value=seite.get("text") or "", height=240, key="ki_web_text")
                frage_web = st.text_input("Frage zur Doku", key="ki_web_frage")
                if st.button("Mit KI auswerten", key="ki_web_ask"):
                    kontext = seite.get("text") or ""
                    with st.spinner(f"KI denkt nach (Timeout: {config.KI_TIMEOUT}s)..."):
                        st.session_state.ki_web_antwort = ai_assistant.frage_an_ki(
                            frage_web or "Fasse die Dokumentation zusammen.",
                            kontext,
                            modell,
                        )
                if st.session_state.get("ki_web_antwort"):
                    st.markdown(st.session_state.ki_web_antwort)
            else:
                st.error(seite.get("fehler") or "Abruf fehlgeschlagen")


# ---------------------------------------------------------------------------
# Agenten-Modus
# ---------------------------------------------------------------------------

def _seite_agent() -> None:
    """🤖 Agenten-Modus – Subagenten für spezialisierte Aufgaben."""
    import agent_manager

    st.markdown("## 🤖 Agenten-Modus")
    st.caption("Spezialisierte KI-Agenten für verschiedene Aufgaben – parallel oder nacheinander.")
    agenten = agent_manager.verfuegbare_agenten()
    with st.container(border=True):
        st.markdown("**📋 Verfügbare Agenten**")
        cols = st.columns(3)
        for i, agent in enumerate(agenten):
            with cols[i % 3]:
                st.markdown(f"**{agent['name']}**")
                st.caption(agent["beschreibung"])

    projekt_pfad = st.text_input(
        "Projektpfad",
        value=st.session_state.get("geladenes_projekt") or "",
        key="agent_projekt",
    )
    aufgabe = st.text_area(
        "Aufgabe",
        height=120,
        key="agent_aufgabe",
        placeholder="z.B. Analysiere die Code-Struktur und finde Verbesserungen",
    )
    auswahl = st.multiselect(
        "Agenten auswählen",
        [a["name"] for a in agenten],
        default=[a["name"] for a in agenten[:3]],
        key="agent_auswahl",
    )
    parallel = st.checkbox("Parallel ausführen", value=True, key="agent_parallel")
    if st.button("🚀 Mission starten", type="primary", key="agent_start"):
        if projekt_pfad and aufgabe:
            agent_ids = [a["id"] for a in agenten if a["name"] in auswahl]
            with st.spinner(f"Agenten arbeiten (Timeout: {config.KI_TIMEOUT}s)..."):
                st.session_state.agent_ergebnis = agent_manager.starte_agenten_mission(
                    aufgabe, projekt_pfad, agent_ids, parallel
                )
                st.rerun()
        else:
            st.warning("Bitte Projektpfad und Aufgabe angeben.")

    if st.session_state.get("agent_ergebnis"):
        ergebnis = st.session_state.agent_ergebnis
        st.markdown("---")
        st.markdown("## 📊 Ergebnisse")
        st.caption(f"Mission: {ergebnis.get('mission')}")
        st.caption(f"Projekt: {ergebnis.get('projekt')}")
        st.caption(f"Zeit: {ergebnis.get('datum')}")
        namen = {a["id"]: a["name"] for a in agenten}
        for agent_name, agent_ergebnis in (ergebnis.get("ergebnisse") or {}).items():
            with st.expander(namen.get(agent_name, agent_name), expanded=True):
                if agent_ergebnis.get("erfolg"):
                    st.success("✅ Erfolg")
                    st.markdown(agent_ergebnis.get("ergebnis") or "")
                else:
                    st.error(f"❌ Fehler: {agent_ergebnis.get('fehler', 'Unbekannt')}")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def _seite_orchestrator() -> None:
    """🚀 Projekt erstellen – komplette Projekte aus einer Idee."""
    import project_orchestrator

    st.markdown("## 🚀 Projekt erstellen")
    st.caption("Gib eine Idee ein – CMM erstellt ein komplettes Projekt mit Struktur, Code und Doku.")
    name = st.text_input("Projektname", key="orch_name", placeholder="z.B. ToDo-App")
    idee = st.text_area(
        "Idee",
        height=150,
        key="orch_idee",
        placeholder="z.B. Eine Web-App mit Flask und SQLite für Aufgabenverwaltung",
    )
    if st.button("🚀 Projekt erstellen", type="primary", key="orch_start"):
        if name and idee:
            with st.spinner(f"Erstelle Projekt (Timeout: {config.KI_TIMEOUT}s)..."):
                st.session_state.orch_ergebnis = project_orchestrator.projekt_erstellen(idee, name)
                st.rerun()
        else:
            st.warning("Bitte Name und Idee angeben.")

    if st.session_state.get("orch_ergebnis"):
        ergebnis = st.session_state.orch_ergebnis
        if ergebnis.get("erfolg"):
            st.success(f"✅ Projekt erstellt: {ergebnis.get('projekt')}")
            st.markdown("**Erstellte Dateien:**")
            for datei in ergebnis.get("dateien") or []:
                st.write(f"- `{datei}`")
            if st.button("📂 Projekt öffnen", key="orch_open"):
                st.session_state.geladenes_projekt = ergebnis.get("projekt")
                if bruecke is not None:
                    bruecke._projekt_laden(ergebnis.get("projekt"))
                _nav_setzen(NAV_FABRIK)
                st.rerun()
        else:
            st.error(f"❌ Fehler: {ergebnis.get('fehler', 'Unbekannt')}")


# ---------------------------------------------------------------------------
# Fabrik
# ---------------------------------------------------------------------------

def _seite_fabrik() -> None:
    if bruecke is None:
        st.error("bruecke.py konnte nicht geladen werden.")
        st.info("Fallback: starte die Fabrik separat mit starte_fabrik.bat")
        return
    bruecke.render(als_subapp=True)


# ---------------------------------------------------------------------------
# Tool 1 System-Check
# ---------------------------------------------------------------------------

def _systembericht_text() -> str:
    zeilen = [
        "Legostein-Zentrale – Systembericht",
        f"Erstellt: {_jetzt_lesbar()}",
        "",
        f"Python: {sys.version.replace(chr(10), ' ')}",
        f"Ausführbar: {sys.executable}",
        f"OS: {platform.platform()}",
        f"Maschine: {platform.machine()}",
        f"Prozessor: {platform.processor() or 'unbekannt'}",
        f"CPU-Kerne: {os.cpu_count()}",
    ]
    if psutil:
        zeilen.append(f"CPU-Auslastung: {psutil.cpu_percent(interval=0.2)} %")
        ram = psutil.virtual_memory()
        zeilen.append(f"RAM: {ram.used/1024**3:.2f}/{ram.total/1024**3:.2f} GB ({ram.percent} %)")
    else:
        zeilen.append("psutil nicht installiert")
    try:
        laufwerk = str(config.BASE_DIR.drive or "I:") + "\\"
        usage = shutil.disk_usage(laufwerk)
        zeilen.append(
            f"Speicher {laufwerk}: {usage.free/1024**3:.2f} GB frei / {usage.total/1024**3:.2f} GB"
        )
    except OSError as fehler:
        zeilen.append(f"Speicherplatz: {fehler}")
    zeilen.append(f"Ollama: {ollama_status()} @ {_ollama_host()}")
    zeilen.append(f"Ollama-Binary: {_ollama_bin() or 'nicht im PATH'}")
    zeilen.append(f"Modelle: {', '.join(modelle_holen()) or '(keine)'}")
    zeilen.append("")
    zeilen.append("Pakete:")
    for name in PAKET_LISTE:
        zeilen.append(f"  - {name}: {_paket_version(name)}")
    return "\n".join(zeilen)


def _tool_system() -> None:
    if "legosteine" not in st.session_state:
        st.session_state.legosteine = []
    if "geladenes_projekt" not in st.session_state:
        st.session_state.geladenes_projekt = ""
    if "ampel_stats" not in st.session_state:
        st.session_state.ampel_stats = {"rot": 0, "gelb": 0, "gruen": 0}

    st.markdown("### 🖥️ System-Check")
    if psutil is None:
        _fehlende_lib("psutil")
    col1, col2 = st.columns(2)
    with col1:
        with st.container(border=True):
            st.write(f"**Python:** {platform.python_version()}")
            st.write(f"**Interpreter:** `{sys.executable}`")
            st.write(f"**OS:** {platform.system()} {platform.release()}")
            st.write(f"**CPU:** {platform.processor() or platform.machine()}")
            st.write(f"**Kerne:** {os.cpu_count() or '?'}")
            if psutil:
                st.write(f"**CPU-Last:** {psutil.cpu_percent(interval=0.2)} %")
                ram = psutil.virtual_memory()
                st.write(f"**RAM:** {ram.percent} % belegt")
    with col2:
        with st.container(border=True):
            try:
                laufwerk = str(config.BASE_DIR.drive or "I:") + "\\"
                usage = shutil.disk_usage(laufwerk)
                st.write(
                    f"**Laufwerk {laufwerk}:** {usage.free/1024**3:.1f} GB frei von {usage.total/1024**3:.1f} GB"
                )
            except OSError as fehler:
                st.write(f"**Laufwerk:** {fehler}")
            st.write(f"**Ollama:** {'🟢 läuft' if ollama_status()=='running' else '🔴 gestoppt'}")
            st.write(f"**Binary:** `{_ollama_bin() or '—'}`")
            st.markdown("**Pakete**")
            for name in PAKET_LISTE:
                st.write(f"- `{name}` { _paket_version(name) }")

    steine = st.session_state.get("legosteine") or []
    projekt = st.session_state.get("geladenes_projekt") or ""
    stats = st.session_state.get("ampel_stats") or {"rot": 0, "gelb": 0, "gruen": 0}
    with st.container(border=True):
        st.markdown("**Geladenes Projekt**")
        if projekt:
            st.write(f"`{projekt}` · {len(steine)} Legosteine")
            st.write(
                f"🔴 {stats.get('rot', 0)} · 🟡 {stats.get('gelb', 0)} · 🟢 {stats.get('gruen', 0)}"
            )
        else:
            st.caption("Kein Projekt geladen – System-Check läuft trotzdem.")

    if st.button("Systembericht exportieren", key="tool_sys_export"):
        pfad = config.BERICHTE_DIR / f"systembericht_{_stempel()}.txt"
        pfad.write_text(_systembericht_text(), encoding="utf-8")
        st.success(f"Gespeichert: {pfad}")
        st.download_button(
            "Download",
            data=pfad.read_text(encoding="utf-8"),
            file_name=pfad.name,
            mime="text/plain",
            key="tool_sys_dl",
        )


# ---------------------------------------------------------------------------
# Tool 2 Health
# ---------------------------------------------------------------------------

def _health_daten(projektname: str) -> dict:
    pfad = config.PROJEKTE_DIR / projektname
    steine = code_wrangler.analysiere_code(pfad)
    funktionen = [s for s in steine if s.get("typ") == "funktion"]
    klassen = [s for s in steine if s.get("typ") == "klasse"]
    rot = [s for s in steine if s.get("ampel") == "🔴"]
    gelb = [s for s in steine if s.get("ampel") == "🟡"]
    gruen = [s for s in steine if s.get("ampel") == "🟢"]
    zeilen_fn = [int(s.get("zeilen") or 0) for s in funktionen]
    schnitt = round(sum(zeilen_fn) / len(zeilen_fn), 1) if zeilen_fn else 0.0
    groesste = max(steine, key=lambda s: (s.get("zeilen") or 0, s.get("parameter") or 0), default=None)
    datei_rot: Counter[str] = Counter(s.get("datei", "") for s in rot)
    return {
        "projekt": projektname,
        "pfad": str(pfad),
        "datum": _jetzt_lesbar(),
        "steine": len(steine),
        "funktionen": len(funktionen),
        "klassen": len(klassen),
        "ampel": {"rot": len(rot), "gelb": len(gelb), "gruen": len(gruen)},
        "zeilen_schnitt_funktion": schnitt,
        "komplexeste": {
            "name": (groesste or {}).get("name"),
            "datei": (groesste or {}).get("datei"),
            "zeilen": (groesste or {}).get("zeilen"),
            "ampel": (groesste or {}).get("ampel"),
        } if groesste else {},
        "dateien_rot": datei_rot.most_common(10),
    }


def _tool_health() -> None:
    st.markdown("### ❤️ Projekt-Health-Check")
    projekte = _projekte()
    if not projekte:
        st.info("Keine Projekte in /PROJEKTE. Lege eines in der Fabrik an.")
        return
    name = st.selectbox("Projekt", projekte, key="tool_health_proj")
    if st.button("Analysieren", key="tool_health_go"):
        st.session_state.tool_health_data = _health_daten(name)
    daten = st.session_state.get("tool_health_data")
    if not daten:
        return
    a, b, c, d = st.columns(4)
    a.metric("Steine", daten["steine"])
    b.metric("Funktionen", daten["funktionen"])
    c.metric("Klassen", daten["klassen"])
    d.metric("Ø Zeilen/Funktion", daten["zeilen_schnitt_funktion"])
    st.write(
        f"Ampel: 🔴 {daten['ampel']['rot']} · 🟡 {daten['ampel']['gelb']} · 🟢 {daten['ampel']['gruen']}"
    )
    komp = daten.get("komplexeste") or {}
    if komp:
        st.write(
            f"Komplexeste: **{komp.get('name')}** in `{komp.get('datei')}` "
            f"({komp.get('zeilen')} Zeilen, {komp.get('ampel')})"
        )
    rot_dateien = daten.get("dateien_rot") or []
    if rot_dateien:
        st.markdown("**Dateien mit den meisten roten Steinen**")
        for datei, anzahl in rot_dateien:
            st.write(f"- `{datei}`: {anzahl}")
    else:
        st.success("Keine roten Steine.")
    if st.button("Health-Bericht erstellen", key="tool_health_export"):
        stempel = _stempel()
        json_pfad = config.BERICHTE_DIR / f"health_{daten['projekt']}_{stempel}.json"
        txt_pfad = config.BERICHTE_DIR / f"health_{daten['projekt']}_{stempel}.txt"
        json_pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
        txt = [
            f"Health-Bericht {daten['projekt']}",
            f"Datum: {daten['datum']}",
            f"Steine: {daten['steine']} (F={daten['funktionen']}, K={daten['klassen']})",
            f"Ampel rot/gelb/gruen: {daten['ampel']['rot']}/{daten['ampel']['gelb']}/{daten['ampel']['gruen']}",
            f"Ø Zeilen/Funktion: {daten['zeilen_schnitt_funktion']}",
            f"Komplexeste: {komp}",
            f"Rote Dateien: {rot_dateien}",
        ]
        txt_pfad.write_text("\n".join(str(x) for x in txt), encoding="utf-8")
        st.success(f"JSON: {json_pfad}\nTXT: {txt_pfad}")


# ---------------------------------------------------------------------------
# Tool 3 Backups
# ---------------------------------------------------------------------------

def _tool_backups() -> None:
    st.markdown("### 💾 Backup-Viewer")
    backups = zeitkapsel.alle_backups()
    if not backups:
        st.info("Keine Backups in /ZEITMASCHINE.")
        return
    zeilen = [
        {
            "Datum": b["datum"],
            "Projekt": b["projektname"],
            "Steine": b["anzahl_legosteine"],
            "Größe MB": b["groesse_mb"],
            "Ordner": b["ordner"],
        }
        for b in backups
    ]
    if PANDAS_OK:
        st.dataframe(pd.DataFrame(zeilen), use_container_width=True, hide_index=True)
    else:
        st.table(zeilen)

    labels = [f"{b['datum']} · {b['projektname']} · {b['ordner']}" for b in backups]
    auswahl = st.selectbox("Backup wählen", labels, key="tool_backup_sel")
    treffer = backups[labels.index(auswahl)] if auswahl in labels else None
    if not treffer:
        return
    st.caption(treffer["pfad"])

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Backup löschen", key="tool_backup_del"):
            st.session_state.backup_loesch_frage = treffer["pfad"]
        if st.session_state.backup_loesch_frage == treffer["pfad"]:
            st.warning("Backup unwiderruflich löschen?")
            j, n = st.columns(2)
            if j.button("Ja, löschen", key="tool_backup_del_yes"):
                meld = zeitkapsel.backup_loeschen(treffer["pfad"])
                st.session_state.backup_loesch_frage = ""
                if meld.get("erfolg"):
                    st.success(meld["meldung"])
                    st.rerun()
                else:
                    st.error(meld["meldung"])
            if n.button("Nein", key="tool_backup_del_no"):
                st.session_state.backup_loesch_frage = ""
                st.rerun()
    with c2:
        if st.button("Backup wiederherstellen", key="tool_backup_restore"):
            st.session_state.backup_restore_frage = treffer["pfad"]
        if st.session_state.backup_restore_frage == treffer["pfad"]:
            st.warning("Projektordner wird durch dieses Backup ersetzt.")
            j, n = st.columns(2)
            if j.button("Ja, wiederherstellen", key="tool_backup_res_yes"):
                meld = zeitkapsel.backup_wiederherstellen(treffer["pfad"])
                st.session_state.backup_restore_frage = ""
                if meld.get("erfolg"):
                    st.success(meld["meldung"])
                else:
                    st.error(meld["meldung"])
            if n.button("Abbrechen", key="tool_backup_res_no"):
                st.session_state.backup_restore_frage = ""
                st.rerun()


# ---------------------------------------------------------------------------
# Tool 4 Prompt-Historie
# ---------------------------------------------------------------------------

def _tool_historie() -> None:
    st.markdown("### 📜 Grok-Prompt-Historie")
    eintraege = config.historie_laden()
    st.caption(f"{len(eintraege)} Einträge in `{config.PROMPT_HISTORIE_DATEI.name}`")
    if st.button("Historie löschen", key="tool_hist_clear"):
        config.historie_loeschen()
        st.success("Historie geleert.")
        st.rerun()
    if not eintraege:
        st.info("Noch keine Prompts. Erzeuge welche in der Legostein-Fabrik.")
        return
    for i, eintrag in enumerate(eintraege):
        problem = str(eintrag.get("problem") or "")
        kurz = problem if len(problem) <= 80 else problem[:77] + "..."
        titel = f"{eintrag.get('datum','')} · {eintrag.get('projekt','')} · {eintrag.get('stein','')} – {kurz}"
        with st.expander(titel, expanded=False):
            st.write(f"**Problem:** {problem or '—'}")
            preview = str(eintrag.get("prompt") or "")
            st.code(preview[:1200] + ("…" if len(preview) > 1200 else ""), language="markdown")
            if st.button("Prompt erneut verwenden", key=f"tool_hist_reuse_{i}"):
                st.session_state.grok_prompt = preview
                st.session_state.problem_text = problem
                _nav_setzen(NAV_FABRIK)
                st.rerun()


# ---------------------------------------------------------------------------
# Tool 5 Statistiken
# ---------------------------------------------------------------------------

def _datei_zeilenstatistik(pfad: Path) -> tuple[int, int, int, int]:
    try:
        text = pfad.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, 0, 0, 0
    code = kommentar = leer = 0
    for zeile in text.splitlines():
        stripped = zeile.strip()
        if not stripped:
            leer += 1
        elif stripped.startswith("#"):
            kommentar += 1
        else:
            code += 1
    return code + kommentar + leer, code, kommentar, leer


def _import_namen(baum) -> list[str]:
    import ast
    namen: list[str] = []
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Import):
            for alias in knoten.names:
                namen.append(alias.name.split(".")[0])
        elif isinstance(knoten, ast.ImportFrom):
            if knoten.module:
                namen.append(knoten.module.split(".")[0])
    return namen


def _stat_daten(projektname: str) -> dict:
    import ast

    wurzel = config.PROJEKTE_DIR / projektname
    gesamt = code = kommentar = leer = dateien = 0
    datei_zeilen: dict[str, int] = {}
    imports: Counter[str] = Counter()
    for dirpfad, dirnamen, dateinamen in os.walk(wurzel):
        dirnamen[:] = [d for d in dirnamen if d not in config.IGNORE_LIST]
        for name in dateinamen:
            if not name.endswith(".py"):
                continue
            pfad = Path(dirpfad) / name
            dateien += 1
            g, c, k, l = _datei_zeilenstatistik(pfad)
            gesamt += g
            code += c
            kommentar += k
            leer += l
            rel = str(pfad.relative_to(wurzel))
            datei_zeilen[rel] = g
            try:
                baum = ast.parse(pfad.read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError):
                continue
            imports.update(_import_namen(baum))
    steine = code_wrangler.analysiere_code(wurzel)
    aufrufe: Counter[str] = Counter()
    for stein in steine:
        aufrufe[stein.get("name", "")] += 0
        for nachbar in stein.get("nachbarn") or []:
            aufrufe[nachbar] += 1
    ampel = Counter(s.get("ampel") for s in steine)
    return {
        "projekt": projektname,
        "dateien": dateien,
        "gesamtzeilen": gesamt,
        "code": code,
        "kommentare": kommentar,
        "leerzeilen": leer,
        "datei_zeilen": datei_zeilen,
        "imports": imports.most_common(20),
        "top_funktionen": aufrufe.most_common(10),
        "ampel": {"🟢": ampel.get("🟢", 0), "🟡": ampel.get("🟡", 0), "🔴": ampel.get("🔴", 0)},
        "steine": len(steine),
    }


def _ampel_chart(ampel: dict) -> None:
    labels = ["Grün", "Gelb", "Rot"]
    werte = [ampel.get("🟢", 0), ampel.get("🟡", 0), ampel.get("🔴", 0)]
    farben = ["#2ecc71", "#f1c40f", "#e74c3c"]
    if PLOTLY_OK and go is not None:
        fig = go.Figure(go.Bar(x=labels, y=werte, marker_color=farben))
        fig.update_layout(
            title="Ampel-Verteilung",
            paper_bgcolor="#2d2d30",
            plot_bgcolor="#2d2d30",
            font_color="#d4d4d4",
            height=320,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart({"Grün": [werte[0]], "Gelb": [werte[1]], "Rot": [werte[2]]})
        if not PLOTLY_OK:
            st.caption("Für Plotly-Diagramme: pip install plotly")


def _datei_pie(datei_zeilen: dict[str, int]) -> None:
    if not datei_zeilen:
        st.info("Keine Dateien.")
        return
    top = sorted(datei_zeilen.items(), key=lambda kv: kv[1], reverse=True)[:8]
    if PLOTLY_OK and go is not None:
        fig = go.Figure(go.Pie(labels=[k for k, _ in top], values=[v for _, v in top], hole=0.35))
        fig.update_layout(
            title="Datei-Anteile (Zeilen)",
            paper_bgcolor="#2d2d30",
            font_color="#d4d4d4",
            height=340,
            margin=dict(l=20, r=20, t=40, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart({k: v for k, v in top})


def _tool_stats() -> None:
    st.markdown("### 📊 Code-Statistiken")
    if not PLOTLY_OK:
        _fehlende_lib("plotly")
    if not PANDAS_OK:
        _fehlende_lib("pandas")
    projekte = _projekte()
    if not projekte:
        st.info("Keine Projekte in /PROJEKTE.")
        return
    name = st.selectbox("Projekt", projekte, key="tool_stat_proj")
    if st.button("Statistik berechnen", key="tool_stat_go"):
        st.session_state.tool_stat_data = _stat_daten(name)
    daten = st.session_state.get("tool_stat_data")
    if not daten:
        return
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Dateien", daten["dateien"])
    m2.metric("Gesamtzeilen", daten["gesamtzeilen"])
    m3.metric("Code", daten["code"])
    m4.metric("Steine", daten["steine"])
    st.caption(
        f"Kommentare: {daten['kommentare']} · Leerzeilen: {daten['leerzeilen']}"
    )
    g1, g2 = st.columns(2)
    with g1:
        _ampel_chart(daten["ampel"])
    with g2:
        _datei_pie(daten["datei_zeilen"])
    st.markdown("**Import-Statistik**")
    if daten["imports"]:
        if PANDAS_OK:
            st.dataframe(
                pd.DataFrame(daten["imports"], columns=["Modul", "Anzahl"]),
                hide_index=True,
                use_container_width=True,
            )
        else:
            for modul, anzahl in daten["imports"]:
                st.write(f"- `{modul}`: {anzahl}")
    st.markdown("**Top 10 meistverwendete Funktionen (Aufrufe als Nachbarn)**")
    if daten["top_funktionen"]:
        for fname, anzahl in daten["top_funktionen"]:
            st.write(f"- `{fname}`: {anzahl}")
    else:
        st.caption("Keine Aufrufe gefunden.")

    if st.button("Statistik exportieren", key="tool_stat_export"):
        stempel = _stempel()
        csv_pfad = config.BERICHTE_DIR / f"statistik_{daten['projekt']}_{stempel}.csv"
        pdf_pfad = config.BERICHTE_DIR / f"statistik_{daten['projekt']}_{stempel}.pdf"
        with csv_pfad.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["feld", "wert"])
            writer.writerow(["projekt", daten["projekt"]])
            writer.writerow(["dateien", daten["dateien"]])
            writer.writerow(["gesamtzeilen", daten["gesamtzeilen"]])
            writer.writerow(["code", daten["code"]])
            writer.writerow(["kommentare", daten["kommentare"]])
            writer.writerow(["leerzeilen", daten["leerzeilen"]])
            writer.writerow([])
            writer.writerow(["datei", "zeilen"])
            for datei, zahl in daten["datei_zeilen"].items():
                writer.writerow([datei, zahl])
            writer.writerow([])
            writer.writerow(["modul", "imports"])
            writer.writerows(daten["imports"])
            writer.writerow([])
            writer.writerow(["funktion", "aufrufe"])
            writer.writerows(daten["top_funktionen"])
        pdf_zeilen = [
            f"Projekt: {daten['projekt']}",
            f"Dateien: {daten['dateien']}",
            f"Zeilen gesamt/code/kommentar/leer: {daten['gesamtzeilen']}/{daten['code']}/{daten['kommentare']}/{daten['leerzeilen']}",
            f"Ampel G/Y/R: {daten['ampel']}",
            "Top-Funktionen: " + ", ".join(f"{n}={a}" for n, a in daten["top_funktionen"]),
            "Imports: " + ", ".join(f"{n}={a}" for n, a in daten["imports"][:10]),
        ]
        _pdf_schreiben(pdf_pfad, "Code-Statistik", pdf_zeilen)
        st.success(f"CSV: {csv_pfad}\nPDF: {pdf_pfad}")


def _seite_tools() -> None:
    st.markdown("## 🛠️ Toolsammlung")
    tabs = st.tabs(
        [
            "🖥️ System-Check",
            "❤️ Health-Check",
            "💾 Backup-Viewer",
            "📜 Prompt-Historie",
            "📊 Code-Statistiken",
            "🧩 Skills",
            "📦 Git",
        ]
    )
    with tabs[0]:
        _tool_system()
    with tabs[1]:
        _tool_health()
    with tabs[2]:
        _tool_backups()
    with tabs[3]:
        _tool_historie()
    with tabs[4]:
        _tool_stats()
    with tabs[5]:
        _tool_skills()
    with tabs[6]:
        _tool_git()


def _tool_skills() -> None:
    """🧩 CMM-Skills – Benutzerdefinierte Workflows."""
    import skill_loader

    st.markdown("### 🧩 CMM-Skills")
    st.caption("Benutzerdefinierte Workflows für wiederkehrende Aufgaben.")
    skills = skill_loader.skills_laden()
    if not skills:
        st.info("Keine Skills gefunden. Erstelle eine YAML/JSON-Datei im SKILLS-Ordner.")
        return
    for skill in skills:
        with st.expander(f"🧩 {skill.get('name', 'Unbekannt')}", expanded=False):
            st.write(skill.get("beschreibung", ""))
            st.caption(f"Datei: {skill.get('_datei', '')}")
            steine = st.session_state.get("legosteine") or []
            if steine and bruecke is not None:
                labels = [bruecke._stein_label(s) for s in steine]
                gewaehlt = st.selectbox(
                    "Legostein wählen",
                    labels,
                    key=f"skill_stein_{skill.get('_datei', '')}",
                )
                if st.button("Skill ausführen", key=f"skill_run_{skill.get('_datei', '')}"):
                    stein = bruecke._stein_finden(gewaehlt) if gewaehlt else None
                    if stein:
                        with st.spinner(f"Führe Skill aus (Timeout: {config.KI_TIMEOUT}s)..."):
                            st.session_state.skill_ergebnis = skill_loader.skill_ausfuehren(
                                skill, stein.get("code", "")
                            )
                            st.rerun()
            else:
                st.caption("Lade zuerst ein Projekt in der Fabrik.")
    if st.session_state.get("skill_ergebnis"):
        ergebnis = st.session_state.skill_ergebnis
        st.markdown(f"**Ergebnis: {ergebnis.get('skill')}**")
        for schritt in ergebnis.get("ergebnisse") or []:
            with st.expander(schritt.get("schritt", "Schritt"), expanded=True):
                if schritt.get("erfolg"):
                    st.markdown(schritt.get("ergebnis") or "")
                else:
                    st.error(schritt.get("fehler") or "Fehler")


def _tool_git() -> None:
    """📦 Git – Status, Diff, Branches, Commit."""
    import git_integration

    st.markdown("### 📦 Git")
    pfad = st.session_state.get("geladenes_projekt") or ""
    if not pfad:
        st.info("Lade zuerst ein Projekt in der Fabrik.")
        return
    if not git_integration.git_ist_repo(pfad):
        st.warning("Dieses Projekt ist kein Git-Repository.")
        return
    if st.button("Status aktualisieren", key="tool_git_status"):
        st.session_state.git_status = git_integration.git_status(pfad)
    status = st.session_state.get("git_status") or git_integration.git_status(pfad)
    if status.get("erfolg"):
        st.write(f"**Branch:** `{status.get('branch')}` · Änderungen: {status.get('anzahl', 0)}")
        for item in status.get("aenderungen") or status.get("änderungen") or []:
            st.write(f"- `{item.get('status')}` {item.get('datei')}")
    else:
        st.error(status.get("fehler") or "Git-Status fehlgeschlagen")
    if st.button("Diff anzeigen", key="tool_git_diff"):
        diff = git_integration.git_diff(pfad)
        st.session_state.git_diff = diff.get("diff") if diff.get("erfolg") else diff.get("fehler")
    if st.session_state.get("git_diff"):
        st.code(st.session_state.git_diff, language="diff")
    branches = git_integration.git_branches(pfad)
    if branches.get("erfolg"):
        st.markdown("**Branches**")
        for b in branches.get("branches") or []:
            st.write(f"- {b}")
    nachricht = st.text_input("Commit-Nachricht", key="tool_git_msg")
    if st.button("Commit (git add . && commit)", key="tool_git_commit"):
        if nachricht.strip():
            result = git_integration.git_commit(pfad, nachricht.strip())
            if result.get("erfolg"):
                st.success(result.get("ausgabe") or "Commit erstellt")
            else:
                st.error(result.get("fehler") or result.get("ausgabe") or "Commit fehlgeschlagen")
        else:
            st.warning("Bitte eine Commit-Nachricht eingeben.")


# ---------------------------------------------------------------------------
# Einstellungen
# ---------------------------------------------------------------------------

def _seite_settings() -> None:
    st.markdown("## ⚙️ Einstellungen")
    aktuell = config.einstellungen_als_dict()
    basis = st.text_input("Projekt-Pfad", value=aktuell["base_dir"], key="set_base")
    host = st.text_input("Ollama-URL", value=aktuell["ollama_host"], key="set_host")
    modelle = modelle_holen()
    vorhandene = modelle or [aktuell["ollama_modell"]]
    if aktuell["ollama_modell"] not in vorhandene:
        vorhandene = [aktuell["ollama_modell"]] + vorhandene
    modell = st.selectbox(
        "Ollama-Modell",
        vorhandene,
        index=vorhandene.index(aktuell["ollama_modell"]) if aktuell["ollama_modell"] in vorhandene else 0,
        key="set_modell",
    )
    backups = st.slider("Max Backups", min_value=1, max_value=20, value=int(aktuell["max_backups"]), key="set_backups")
    nachbarn = st.slider("Max Nachbarn", min_value=1, max_value=10, value=int(aktuell["max_nachbarn"]), key="set_nachbarn")
    diff = st.slider("Diff-Schwelle (%)", min_value=5, max_value=50, value=int(aktuell["diff_schwelle"]), key="set_diff")
    timeout = st.slider(
        "KI-Timeout (Sekunden)",
        min_value=30,
        max_value=1200,
        value=int(aktuell.get("ki_timeout", 600)),
        step=30,
        key="set_timeout",
        help="Maximale Wartezeit für KI-Antworten. Größere Modelle brauchen mehr Zeit.",
    )
    st.caption("Einstellungen werden nach settings.json und in die Konstanten von config.py geschrieben.")
    if st.button("Einstellungen speichern", type="primary", key="set_save"):
        config.einstellungen_speichern(
            {
                "base_dir": basis.strip() or str(config.BASE_DIR),
                "ollama_host": host.strip() or "http://localhost:11434",
                "ollama_modell": modell,
                "max_backups": backups,
                "max_nachbarn": nachbarn,
                "diff_schwelle": diff,
                "ki_timeout": timeout,
            }
        )
        for ordner in (
            config.PROJEKTE_DIR,
            config.ZEITMASCHINE_DIR,
            config.SANDBOX_DIR,
            config.BERICHTE_DIR,
        ):
            ordner.mkdir(parents=True, exist_ok=True)
        st.success(f"Gespeichert in {config.SETTINGS_DATEI} und config.py")

    st.markdown("---")
    st.markdown("### 🔑 Lizenz")
    aktueller_key = key_manager.lizenz_laden()
    if aktueller_key:
        ergebnis = key_manager.validiere_key(aktueller_key)
        if ergebnis["valid"] and not ergebnis.get("abgelaufen", False):
            st.success(f"✅ **{ergebnis['name']}** – gültig bis {ergebnis['ablaufdatum']}")
        else:
            st.error(f"❌ {ergebnis.get('fehler') or 'Ungültige oder abgelaufene Lizenz'}")

    neuer_key = st.text_input("Lizenz-Key eingeben", type="password", key="lizenz_key")
    if st.button("Lizenz speichern", key="lizenz_speichern"):
        if neuer_key.strip():
            ergebnis = key_manager.validiere_key(neuer_key.strip())
            if ergebnis["valid"] and not ergebnis.get("abgelaufen", False):
                key_manager.lizenz_speichern(neuer_key.strip())
                st.success("✅ Lizenz gespeichert! Bitte Seite neu laden.")
                st.rerun()
            else:
                st.error(f"❌ {ergebnis.get('fehler', 'Ungültiger Key')}")
        else:
            st.warning("Bitte einen Key eingeben.")

    if aktueller_key:
        if st.button("Lizenz löschen", key="lizenz_loeschen"):
            key_manager.lizenz_loeschen()
            st.rerun()

    # ─── GITHUB-VERTRIEB ───
    st.markdown("---")
    st.markdown("### 🚀 CMM auf GitHub veröffentlichen")
    st.caption("Veröffentliche CMM 8.0 automatisch auf GitHub – Repository, Dateien, Release.")
    if st.button("🚀 CMM auf GitHub veröffentlichen", key="cmm_github_deploy", type="primary"):
        with st.spinner("Veröffentliche CMM auf GitHub..."):
            import github_explorer
            ergebnis = github_explorer.cmm_auf_github_veroeffentlichen()
            if ergebnis.get("repository"):
                st.success("✅ Repository erstellt/gefunden")
            if ergebnis.get("dateien"):
                st.success(f"✅ {len(ergebnis['dateien'])} Dateien hochgeladen")
            if ergebnis.get("release"):
                st.success("✅ Release v8.0 erstellt")
            if ergebnis.get("fehler"):
                for fehler in ergebnis["fehler"]:
                    st.warning(f"⚠️ {fehler}")
            st.markdown(f"""
            🔗 **Repository:** https://github.com/GabelGold/Code_Maker_Matrix
            📦 **Release:** https://github.com/GabelGold/Code_Maker_Matrix/releases
            """)

    st.caption("(c) 2026 Christian Schmitt, Solingen, Germany · c.schmitt@me.com")


# ---------------------------------------------------------------------------
# Einstieg
# ---------------------------------------------------------------------------

def main() -> None:
    _seite_vorbereiten()
    if not _lizenz_status()["ok"]:
        _lizenz_pruefen()
        _seite_lizenz_eingabe()
        return
    nav = _seitenleiste()
    if nav == NAV_START:
        _seite_start()
    elif nav == NAV_ENTDECKEN:
        _seite_entdecken()
    elif nav == NAV_KI:
        _seite_ki()
    elif nav == NAV_AGENT:
        _seite_agent()
    elif nav == NAV_FABRIK:
        _seite_fabrik()
    elif nav == NAV_TOOLS:
        _seite_tools()
    elif nav == NAV_ORCHESTRATOR:
        _seite_orchestrator()
    else:
        _seite_settings()


if __name__ == "__main__":
    main()