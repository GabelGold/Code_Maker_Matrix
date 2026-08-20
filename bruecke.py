# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Legostein-Fabrik Oberfläche

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime
from pathlib import Path

import config
import code_wrangler
import zeitkapsel

try:
    import streamlit as st
except ImportError:  # Benötigt: pip install streamlit
    raise SystemExit(
        "streamlit fehlt. Bitte ausführen: pip install streamlit\n"
        "Danach: starte_fabrik.bat oder 'streamlit run bruecke.py'"
    )

try:
    from pyvis.network import Network

    PYVIS_VERFUEGBAR = True
except ImportError:  # Benötigt: pip install pyvis
    Network = None
    PYVIS_VERFUEGBAR = False


def _session_vorbereiten() -> None:
    vorgaben = {
        "geladenes_projekt": "",
        "legosteine": [],
        "beschreibungen": {},
        "diff_status": None,
        "dateibaum": "",
        "grok_prompt": "",
        "grok_antwort": "",
        "ampel_stats": {"rot": 0, "gelb": 0, "gruen": 0},
        "sandbox_ergebnis": None,
        "ausgewaehlter_stein": "",
        "ki_fortschritt": 0.0,
        "statusmeldung": "",
        "letzter_panic": None,
        "geparster_code": "",
        "prompt_nachbarn": [],
        "panic_frage": False,
        "fortschritt_text": "Bereit.",
        "code_uebernommen": None,
    }
    for schluessel, wert in vorgaben.items():
        if schluessel not in st.session_state:
            st.session_state[schluessel] = wert


def _status(text: str, fortschritt: float | None = None) -> None:
    st.session_state.statusmeldung = text
    st.session_state.fortschritt_text = text
    if fortschritt is not None:
        st.session_state.ki_fortschritt = max(0.0, min(1.0, float(fortschritt)))


def _projekte_im_ordner() -> list[str]:
    if not config.PROJEKTE_DIR.exists():
        return []
    return sorted(
        [p.name for p in config.PROJEKTE_DIR.iterdir() if p.is_dir() and p.name not in config.IGNORE_LIST]
    )


def _ampel_rang(ampel: str) -> int:
    return {"🔴": 3, "🟡": 2, "🟢": 1}.get(ampel, 0)


def _statistiken(steine: list[dict]) -> dict:
    rot = sum(1 for s in steine if s.get("ampel") == "🔴")
    gelb = sum(1 for s in steine if s.get("ampel") == "🟡")
    gruen = sum(1 for s in steine if s.get("ampel") == "🟢")
    return {"rot": rot, "gelb": gelb, "gruen": gruen}


def _dateibaum_bauen(projekt_pfad: str, steine: list[dict]) -> str:
    ampel_je_datei: dict[str, str] = {}
    for stein in steine:
        datei = stein.get("datei", "")
        ampel = stein.get("ampel", "🟢")
        if _ampel_rang(ampel) > _ampel_rang(ampel_je_datei.get(datei, "🟢")):
            ampel_je_datei[datei] = ampel

    zeilen: list[str] = []
    wurzel = Path(projekt_pfad)
    if not wurzel.exists():
        return "(Ordner nicht gefunden)"

    for dirpfad, dirnamen, dateinamen in os.walk(wurzel):
        dirnamen[:] = [d for d in dirnamen if d not in config.IGNORE_LIST]
        rel = Path(dirpfad).relative_to(wurzel)
        tiefe = 0 if str(rel) == "." else len(rel.parts)
        if str(rel) != ".":
            zeilen.append(("    " * (tiefe - 1)) + "📁 " + rel.name)
        for dateiname in sorted(dateinamen):
            rel_datei = str((Path(dirpfad) / dateiname).relative_to(wurzel))
            if dateiname.endswith(".py"):
                ampel = ampel_je_datei.get(rel_datei, "")
                emoji = "⚠️" if ampel == "🔴" else "🧩"
                suffix = f" {ampel}" if ampel else ""
            else:
                emoji = "📄"
                suffix = ""
            zeilen.append(("    " * tiefe) + f"{emoji} {dateiname}{suffix}")
    return "\n".join(zeilen) if zeilen else "(leer)"


def _stein_label(stein: dict) -> str:
    return (
        f"{stein.get('ampel', '')} {stein.get('typ', '')}:{stein.get('name', '')}  "
        f"({stein.get('datei', '')}:{stein.get('lineno', '?')})"
    )


def _stein_finden(label: str) -> dict | None:
    for stein in st.session_state.legosteine:
        if _stein_label(stein) == label:
            return stein
    return None


def _beschreibung_fuer(stein: dict) -> str:
    label = _stein_label(stein)
    return (
        stein.get("beschreibung")
        or st.session_state.beschreibungen.get(label)
        or stein.get("docstring")
        or "Unbekannter Stein"
    )


def _projektname_saeubern(name: str) -> str:
    roh = (name or "").strip()
    sicher = "".join(ch for ch in roh if ch.isalnum() or ch in ("_", "-", " ")).strip()
    sicher = re.sub(r"\s+", "_", sicher)
    return sicher


def _neues_projekt_anlegen(name: str) -> None:
    sicher = _projektname_saeubern(name)
    if not sicher:
        _status("Ungültiger Projektname.")
        return
    config.PROJEKTE_DIR.mkdir(parents=True, exist_ok=True)
    ziel = config.PROJEKTE_DIR / sicher
    if not ziel.exists():
        ziel.mkdir(parents=True, exist_ok=True)
        (ziel / "main.py").write_text(
            '"""Neues Projekt der Legostein-Fabrik."""\n\n\n'
            "def start():\n"
            '    """Einstiegspunkt – hier beginnt die Arbeit."""\n'
            '    print("Hallo Legostein-Fabrik")\n',
            encoding="utf-8",
        )
        _status(f"Projekt angelegt: {ziel}")
    else:
        _status(f"Projekt existiert bereits und wird geladen: {ziel}")
    _projekt_laden(str(ziel))


def _projekt_laden(pfad: str, mit_backup: bool = True) -> None:
    pfad = str(Path(pfad).expanduser())
    if not pfad or not Path(pfad).is_dir():
        _status(f"Pfad ist kein Ordner: {pfad}", 0.0)
        return

    _status("Analysiere Projekt...", 0.15)
    steine = code_wrangler.analysiere_code(pfad)

    if mit_backup:
        try:
            zeitkapsel.backup_erstellen(pfad, anzahl_legosteine=len(steine))
        except (OSError, ValueError) as fehler:
            _status(f"Backup fehlgeschlagen: {fehler}")

    st.session_state.geladenes_projekt = pfad
    st.session_state.legosteine = steine
    st.session_state.beschreibungen = {}
    st.session_state.diff_status = None
    st.session_state.sandbox_ergebnis = None
    st.session_state.geparster_code = ""
    st.session_state.code_uebernommen = None
    st.session_state.ampel_stats = _statistiken(steine)
    st.session_state.dateibaum = _dateibaum_bauen(pfad, steine)
    st.session_state.grok_prompt = ""
    st.session_state.prompt_nachbarn = []
    _status(
        f"Projekt geladen: {pfad}  |  {len(steine)} Legosteine gefunden"
        + (", Backup angelegt." if mit_backup else "."),
        1.0 if steine else 0.0,
    )


def _durchleuchten() -> None:
    pfad = st.session_state.geladenes_projekt
    if not pfad:
        _status("Kein Projekt geladen – zuerst öffnen oder anlegen.")
        return
    _status("Analysiere Projekt...", 0.2)
    steine = code_wrangler.analysiere_code(pfad)
    st.session_state.legosteine = steine
    st.session_state.ampel_stats = _statistiken(steine)
    st.session_state.dateibaum = _dateibaum_bauen(pfad, steine)
    _status(f"Durchleuchtet: {len(steine)} Legosteine.", 1.0 if steine else 0.0)


def _beschreibungen_holen() -> None:
    steine = st.session_state.legosteine
    if not steine:
        _status("Keine Steine zum Beschreiben.")
        return
    gesamt = max(len(steine), 1)
    beschreibungen: dict[str, str] = {}
    fortschritt = st.progress(0.0, text="KI-Beschreibungen werden geholt (0/{})".format(len(steine)))
    for index, stein in enumerate(steine, start=1):
        text_status = f"KI-Beschreibungen werden geholt ({index}/{len(steine)})"
        _status(text_status, index / gesamt)
        fortschritt.progress(index / gesamt, text=text_status)
        schluessel = _stein_label(stein)
        text = code_wrangler.hole_ki_beschreibung(stein.get("code", ""))
        beschreibungen[schluessel] = text
        stein["beschreibung"] = text
    st.session_state.beschreibungen = beschreibungen
    _status("KI-Beschreibungen fertig.", 1.0)
    fortschritt.progress(1.0, text="KI-Beschreibungen fertig")


def _grok_prompt_bauen(problem: str, stein: dict) -> str:
    nachbarn = stein.get("nachbarn") or []
    nachbar_text = ", ".join(nachbarn) if nachbarn else "(keine)"
    beschreibung = _beschreibung_fuer(stein)
    async_flag = "ja" if stein.get("ist_async") else "nein"
    docstring = stein.get("docstring") or "(keiner)"
    return (
        "Du arbeitest an einem Python-Projekt in der Legostein-Fabrik.\n"
        "Ändere NUR den genannten Stein. Liefere den vollständigen neuen Code "
        "für genau diese Stelle, ohne Erklärungen außerhalb des Codeblocks.\n\n"
        f"Problem auf Deutsch:\n{problem.strip()}\n\n"
        f"Stein: {stein.get('name')} ({stein.get('typ')})\n"
        f"Datei: {stein.get('datei')}\n"
        f"Zeile: {stein.get('lineno')}\n"
        f"Ampel: {stein.get('ampel')}\n"
        f"Zeilen / Parameter: {stein.get('zeilen')} / {stein.get('parameter')}\n"
        f"async: {async_flag}\n"
        f"Imports in der Datei: {stein.get('anzahl_imports', 0)}\n"
        f"Docstring: {docstring}\n"
        f"Beschreibung: {beschreibung}\n"
        f"Nachbarn (max. {config.MAX_NACHBARN}, aus finde_nachbarn): {nachbar_text}\n\n"
        "Aktueller Code:\n"
        "```python\n"
        f"{stein.get('code', '')}\n"
        "```\n"
    )


def _code_aus_antwort(text: str) -> str:
    if not text:
        return ""
    if "```" not in text:
        return text.strip()
    treffer = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if treffer:
        return treffer[0].strip()
    teile = text.split("```")
    for teil in teile:
        bereinigt = teil.strip()
        if bereinigt.lower().startswith("python"):
            bereinigt = bereinigt[6:].lstrip()
        if bereinigt:
            return bereinigt
    return text.strip()


def _diff_als_html(diff_text: str) -> str:
    if not diff_text:
        return "<pre style='font-size:0.85rem'>(keine Unterschiede)</pre>"
    zeilen_html: list[str] = []
    for zeile in diff_text.splitlines():
        sicher = html.escape(zeile)
        if zeile.startswith("+") and not zeile.startswith("+++"):
            zeilen_html.append(
                f"<span style='color:#0b6b2c;background:#e7f8ec'>{sicher}</span>"
            )
        elif zeile.startswith("-") and not zeile.startswith("---"):
            zeilen_html.append(
                f"<span style='color:#9b1c1c;background:#fdeaea'>{sicher}</span>"
            )
        else:
            zeilen_html.append(f"<span>{sicher}</span>")
    return (
        "<pre style='font-size:0.82rem;line-height:1.35;white-space:pre-wrap'>"
        + "<br>".join(zeilen_html)
        + "</pre>"
    )


def _zwischenablage_html(text: str) -> None:
    payload = json.dumps(text)
    st.components.v1.html(
        f"""
        <button id="copy-btn" style="padding:6px 12px;cursor:pointer;">
            In die Zwischenablage kopieren
        </button>
        <span id="copy-ok" style="margin-left:8px;font-family:sans-serif;font-size:0.9rem;"></span>
        <script>
        const payload = {payload};
        const btn = document.getElementById("copy-btn");
        btn.addEventListener("click", async () => {{
            try {{
                await navigator.clipboard.writeText(payload);
                document.getElementById("copy-ok").innerText = "Kopiert.";
            }} catch (err) {{
                document.getElementById("copy-ok").innerText =
                    "Kopieren blockiert – nutze das Code-Feld (Kopier-Symbol).";
            }}
        }});
        </script>
        """,
        height=42,
    )


def _graph_html(steine: list[dict]) -> str | None:
    if not PYVIS_VERFUEGBAR or Network is None or not steine:
        return None
    netz = Network(height="620px", width="100%", bgcolor="#ffffff", font_color="#111111")
    netz.barnes_hut()
    try:
        netz.set_options(
            """
            {
              "interaction": {
                "dragNodes": true,
                "dragView": true,
                "zoomView": true,
                "navigationButtons": true,
                "keyboard": true,
                "tooltipDelay": 180
              },
              "physics": {
                "enabled": true,
                "barnesHut": {
                  "gravitationalConstant": -8000,
                  "springLength": 140
                }
              }
            }
            """
        )
    except Exception:
        pass
    farben = {"🟢": "#2ecc71", "🟡": "#f1c40f", "🔴": "#e74c3c"}
    stein_daten: dict[str, dict] = {}
    bekannte = {stein["name"] for stein in steine}
    for stein in steine:
        knoten_id = _stein_label(stein)
        titel = (
            f"{stein.get('name')}\n{stein.get('datei')}\n"
            f"{stein.get('zeilen')} Zeilen, {stein.get('parameter')} Parameter"
        )
        netz.add_node(
            knoten_id,
            label=f"{stein.get('ampel')} {stein.get('name')}",
            title=titel,
            color=farben.get(stein.get("ampel", "🟢"), "#95a5a6"),
            shape="box" if stein.get("typ") == "klasse" else "ellipse",
        )
        stein_daten[knoten_id] = {
            "name": stein.get("name", ""),
            "ampel": stein.get("ampel", ""),
            "beschreibung": _beschreibung_fuer(stein),
            "nachbarn": ", ".join(stein.get("nachbarn") or []) or "—",
            "code": stein.get("code") or "",
            "datei": stein.get("datei", ""),
            "docstring": stein.get("docstring") or "",
        }
    vorhandene = {_stein_label(s) for s in steine}
    for stein in steine:
        quelle = _stein_label(stein)
        for nachbar in stein.get("nachbarn") or []:
            ziel = None
            nachbar_kurz = nachbar.split(".")[-1]
            for kandidat in steine:
                if kandidat.get("name") in (nachbar, nachbar_kurz):
                    ziel = _stein_label(kandidat)
                    break
            if ziel and ziel in vorhandene:
                netz.add_edge(quelle, ziel, arrows="to")
            elif nachbar not in bekannte:
                extra_id = f"ext:{nachbar}"
                if extra_id not in vorhandene:
                    netz.add_node(extra_id, label=nachbar, color="#bdc3c7", shape="dot")
                    vorhandene.add(extra_id)
                    stein_daten[extra_id] = {
                        "name": nachbar,
                        "ampel": "⚪",
                        "beschreibung": "Externer / importierter Nachbar",
                        "nachbarn": "—",
                        "code": "",
                        "datei": "",
                        "docstring": "",
                    }
                netz.add_edge(quelle, extra_id, arrows="to")

    html_text = netz.generate_html()
    popup = f"""
<div id="stein-popup" style="display:none;position:absolute;top:12px;right:12px;width:340px;
 max-height:90%;overflow:auto;background:#fff;border:1px solid #bbb;padding:12px;z-index:9999;
 box-shadow:0 6px 18px rgba(0,0,0,.18);font-family:sans-serif;font-size:13px;">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
    <strong id="stein-popup-titel">Stein</strong>
    <button onclick="document.getElementById('stein-popup').style.display='none'">Schließen</button>
  </div>
  <div id="stein-popup-inhalt"></div>
</div>
<script>
const STEIN_DATEN = {json.dumps(stein_daten, ensure_ascii=False)};
function escapeHtml(value) {{
  return String(value || "").replace(/[&<>]/g, function(c) {{
    return {{"&":"&amp;","<":"&lt;",">":"&gt;"}}[c];
  }});
}}
function bindSteinClicks() {{
  if (typeof network === "undefined") {{
    setTimeout(bindSteinClicks, 200);
    return;
  }}
  network.on("click", function(params) {{
    if (!params.nodes.length) return;
    const id = params.nodes[0];
    const d = STEIN_DATEN[id];
    if (!d) return;
    document.getElementById("stein-popup-titel").innerText = (d.ampel || "") + " " + (d.name || "");
    document.getElementById("stein-popup-inhalt").innerHTML =
      "<p><b>Ampel:</b> " + escapeHtml(d.ampel) + "</p>" +
      "<p><b>Datei:</b> " + escapeHtml(d.datei) + "</p>" +
      "<p><b>Beschreibung:</b> " + escapeHtml(d.beschreibung) + "</p>" +
      "<p><b>Nachbarn:</b> " + escapeHtml(d.nachbarn) + "</p>" +
      "<pre style='white-space:pre-wrap;background:#f6f6f6;padding:8px;'>" +
      escapeHtml(d.code) + "</pre>";
    document.getElementById("stein-popup").style.display = "block";
  }});
}}
bindSteinClicks();
</script>
"""
    if "</body>" in html_text:
        html_text = html_text.replace("</body>", popup + "</body>")
    else:
        html_text += popup
    return html_text


def _stein_details_inhalt(stein: dict) -> None:
    st.header(f"{stein.get('ampel')} {stein.get('name')}")
    st.caption(f"{stein.get('typ')} · {stein.get('datei')}:{stein.get('lineno')}")
    st.markdown(f"**Ampel:** {stein.get('ampel')}")
    st.markdown(
        f"**Zeilen / Parameter:** {stein.get('zeilen')} / {stein.get('parameter')}  \n"
        f"**async:** {'ja' if stein.get('ist_async') else 'nein'}  \n"
        f"**Imports in der Datei:** {stein.get('anzahl_imports', 0)}"
    )
    st.markdown("**Beschreibung**")
    st.write(_beschreibung_fuer(stein))
    if stein.get("docstring"):
        st.markdown("**Docstring**")
        st.write(stein.get("docstring"))
    nachbarn = stein.get("nachbarn") or []
    st.markdown("**Nachbarn**")
    st.write(", ".join(nachbarn) if nachbarn else "—")
    st.markdown("**Vollständiger Code**")
    st.code(stein.get("code") or "", language="python")


def _sidebar_stein_anzeigen(stein: dict) -> None:
    if st.session_state.get("_fabrik_subapp"):
        with st.expander(
            f"Details: {stein.get('ampel')} {stein.get('name')}",
            expanded=True,
        ):
            _stein_details_inhalt(stein)
        return
    with st.sidebar:
        _stein_details_inhalt(stein)


def _karten_anzeigen(steine: list[dict]) -> None:
    if not steine:
        st.info("Keine Legosteine geladen. Links ein Projekt öffnen.")
        return
    for stein in steine:
        nachbarn = stein.get("nachbarn") or []
        pfeile = " → ".join(nachbarn) if nachbarn else "—"
        titel = (
            f"{stein.get('ampel')} {stein.get('name')} · `{stein.get('typ')}` "
            f"({stein.get('datei')}:{stein.get('lineno')})"
        )
        with st.expander(titel, expanded=False):
            st.caption(
                f"{stein.get('zeilen')} Zeilen  ·  {stein.get('parameter')} Parameter  ·  "
                f"async={'ja' if stein.get('ist_async') else 'nein'}  ·  "
                f"Imports={stein.get('anzahl_imports', 0)}"
            )
            st.write(_beschreibung_fuer(stein))
            st.markdown(f"Nachbarn: {pfeile}")
            st.code(stein.get("code") or "", language="python")


def _neues_projekt_ui() -> None:
    def _formular() -> None:
        name = st.text_input("Projektname", key="neues_projekt_name")
        if st.button("Anlegen und öffnen", key="neues_projekt_go", use_container_width=True):
            _neues_projekt_anlegen(name)

    if hasattr(st, "popover"):
        with st.popover("Neues Projekt anlegen"):
            _formular()
    else:
        with st.expander("Neues Projekt anlegen"):
            _formular()


def _linke_spalte() -> None:
    st.subheader("Projekt-Explorer")
    _neues_projekt_ui()

    vorhandene = _projekte_im_ordner()
    auswahl = st.selectbox(
        "Projekte in /PROJEKTE",
        options=["(keins)"] + vorhandene,
        index=0,
        key="dropdown_projekte",
    )
    if st.button("Aus /PROJEKTE öffnen", use_container_width=True):
        if auswahl != "(keins)":
            _projekt_laden(str(config.PROJEKTE_DIR / auswahl))

    pfad_eingabe = st.text_input(
        "Oder Projektpfad eingeben",
        value=st.session_state.geladenes_projekt,
        placeholder=r"I:\Nicht_Programierer_Matrix\PROJEKTE\mein_projekt",
        key="pfad_eingabe",
    )
    if st.button("Projekt öffnen", use_container_width=True):
        _projekt_laden(pfad_eingabe.strip())

    if st.button("Durchleuchten (AST-Scan)", use_container_width=True):
        if st.session_state.geladenes_projekt:
            _durchleuchten()
        elif pfad_eingabe.strip():
            _projekt_laden(pfad_eingabe.strip())
        else:
            _status("Kein Projekt geladen.")

    st.markdown("---")
    st.subheader("Dateibaum")
    if st.session_state.dateibaum:
        st.code(st.session_state.dateibaum, language=None)
    else:
        st.caption("Noch kein Projekt geladen. Emojis: 📄 Datei  ⚠️ kritische .py  🧩 Python-Modul")

    st.markdown("---")
    st.subheader("Komplexitäts-Übersicht")
    stats = st.session_state.ampel_stats
    st.markdown(
        f"🔴 {stats['rot']} kritische Steine, "
        f"🟡 {stats['gelb']} mittlere, "
        f"🟢 {stats['gruen']} einfache"
    )
    if st.session_state.geladenes_projekt:
        st.caption(f"Aktiv: {st.session_state.geladenes_projekt}")
        if st.button("KI-Beschreibungen holen (Ollama)", use_container_width=True):
            _beschreibungen_holen()
        if st.button("⚡ Alle Steine optimieren", use_container_width=True, key="batch_opt"):
            import batch_processor

            with st.spinner("Optimiere Steine parallel..."):
                st.session_state.batch_ergebnis = batch_processor.batch_optimieren(
                    st.session_state.geladenes_projekt
                )
            st.rerun()
        import git_integration
        import vscode_export

        if git_integration.git_ist_repo(st.session_state.geladenes_projekt):
            if st.button("📦 Git-Status", use_container_width=True, key="git_status"):
                st.session_state.git_status = git_integration.git_status(
                    st.session_state.geladenes_projekt
                )
        if st.button("📂 In VS Code öffnen", use_container_width=True, key="vscode_open"):
            ergebnis = vscode_export.in_vscode_oeffnen(st.session_state.geladenes_projekt)
            if ergebnis.get("erfolg"):
                st.success(ergebnis.get("meldung"))
            else:
                st.error(ergebnis.get("meldung"))
        if st.session_state.get("batch_ergebnis"):
            batch = st.session_state.batch_ergebnis
            st.caption(
                f"Batch: {batch.get('erfolgreich', 0)} ok / {batch.get('fehlgeschlagen', 0)} fehl"
            )
        if st.session_state.get("git_status"):
            gs = st.session_state.git_status
            if gs.get("erfolg"):
                st.caption(f"Git {gs.get('branch')} · {gs.get('anzahl', 0)} Änderungen")
            else:
                st.caption(gs.get("fehler") or "Git-Fehler")


def _mittlere_spalte() -> None:
    st.subheader("Legostein-Graph")
    steine = st.session_state.legosteine
    if not steine:
        st.info("Sobald ein Projekt geladen ist, erscheinen hier die Steine.")
        return

    labels = [_stein_label(s) for s in steine]
    gewaehlt = st.selectbox(
        "Stein in der Seitenleiste öffnen",
        options=["(keiner)"] + labels,
        key="sidebar_stein",
    )
    if gewaehlt and gewaehlt != "(keiner)":
        stein = _stein_finden(gewaehlt)
        if stein:
            _sidebar_stein_anzeigen(stein)

    if PYVIS_VERFUEGBAR:
        st.caption("Ziehen, zoomen, Klick auf Knoten öffnet ein Popup mit Code, Ampel und Nachbarn.")
        graph = _graph_html(steine)
        if graph:
            st.components.v1.html(graph, height=660, scrolling=True)
        else:
            _karten_anzeigen(steine)
    else:
        st.caption(
            "pyvis fehlt – klappbare Kärtchen. Klick öffnet den Code. Benötigt: pip install pyvis"
        )
        _karten_anzeigen(steine)


def _sandbox_details(status: dict) -> None:
    st.markdown("**Detaillierte Testergebnisse**")
    if status.get("zeitstempel"):
        st.caption(f"Zeitstempel: {status.get('zeitstempel')}")

    syntax_ok = bool(status.get("syntax_ok"))
    if syntax_ok:
        st.success("Syntax: Bestanden")
    else:
        zeile = status.get("syntax_zeile")
        extra = f" (Fehlerzeile {zeile})" if zeile else ""
        st.error(f"Syntax: Fehlgeschlagen{extra}")
        if status.get("syntax_fehler"):
            st.code(status.get("syntax_fehler"), language=None)

    st.info(f"Diff-Prozentsatz: {status.get('aenderung_prozent', 0)} %")

    if status.get("import_ok"):
        st.success(f"Import-Test: Bestanden (`import {status.get('modulname', '')}`)")
    else:
        st.error("Import-Test: Fehlgeschlagen")
        if status.get("import_fehler"):
            st.code(status.get("import_fehler"), language=None)

    hinzu = int(status.get("zeilen_hinzugefuegt") or 0)
    weg = int(status.get("zeilen_geloescht") or 0)
    st.markdown(f"**Diff-Zusammenfassung:** {hinzu} Zeilen hinzugefügt, {weg} Zeilen gelöscht")


def _rechte_spalte() -> None:
    st.subheader("Kommandozentrale")
    labels = [_stein_label(s) for s in st.session_state.legosteine]
    if labels:
        gewaehlt = st.selectbox("Legostein wählen", options=labels, key="stein_select")
        st.session_state.ausgewaehlter_stein = gewaehlt
    else:
        st.caption("Keine Steine – zuerst ein Projekt laden.")
        gewaehlt = ""

    problem = st.text_area(
        "Dein Problem auf Deutsch",
        height=120,
        placeholder="z. B. Die Funktion rechnet den Rabatt falsch.",
        key="problem_text",
    )

    if st.button("Prompt für Grok generieren", use_container_width=True):
        stein = _stein_finden(gewaehlt) if gewaehlt else None
        if stein is None:
            _status("Kein Legostein ausgewählt.")
        elif not problem.strip():
            _status("Bitte zuerst das Problem auf Deutsch beschreiben.")
        else:
            stein = dict(stein)
            stein["nachbarn"] = code_wrangler.finde_nachbarn(
                stein.get("code", ""),
                stein.get("name", ""),
                {
                    "namen": stein.get("import_namen") or [],
                    "modul_von": stein.get("import_module") or {},
                    "original_von": stein.get("import_original") or {},
                },
            )
            st.session_state.prompt_nachbarn = list(stein.get("nachbarn") or [])
            st.session_state.grok_prompt = _grok_prompt_bauen(problem, stein)
            try:
                config.historie_hinzufuegen(
                    {
                        "datum": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "projekt": Path(st.session_state.geladenes_projekt).name
                        if st.session_state.geladenes_projekt
                        else "",
                        "stein": stein.get("name", ""),
                        "problem": problem.strip(),
                        "prompt": st.session_state.grok_prompt,
                    }
                )
            except OSError:
                pass
            _status("Grok-Prompt erzeugt.")

    st.markdown("**Grok-Prompt**")
    if st.session_state.grok_prompt:
        st.code(st.session_state.grok_prompt, language="markdown")
        _zwischenablage_html(st.session_state.grok_prompt)
        nachbarn = st.session_state.prompt_nachbarn or []
        if nachbarn:
            st.caption("Inkludierte Nachbarn: " + ", ".join(nachbarn))
        else:
            st.caption("Inkludierte Nachbarn: (keine)")
    else:
        st.caption("Noch kein Prompt erzeugt.")

    st.text_area(
        "Grok's Antwort hier einfügen",
        height=180,
        key="grok_antwort",
    )
    if st.button("Antwort parsen", use_container_width=True):
        st.session_state.geparster_code = _code_aus_antwort(st.session_state.get("grok_antwort", ""))
        if st.session_state.geparster_code:
            _status("Code-Block aus der Antwort extrahiert.")
        else:
            _status("Kein Code-Block gefunden.")

    if st.session_state.geparster_code:
        st.markdown("**Extrahierter Code**")
        st.code(st.session_state.geparster_code, language="python")

    sandbox_ok = bool(
        st.session_state.diff_status and st.session_state.diff_status.get("erfolg")
    )
    start_label = "Sandbox-Test starten ✅" if sandbox_ok else "Sandbox-Test starten"
    if st.button(
        start_label,
        use_container_width=True,
        type="primary" if sandbox_ok else "secondary",
    ):
        stein = _stein_finden(gewaehlt) if gewaehlt else None
        antwort = st.session_state.get("grok_antwort", "")
        if not st.session_state.geladenes_projekt:
            _status("Kein Projekt geladen.")
        elif stein is None:
            _status("Kein Legostein ausgewählt.")
        elif not str(antwort).strip():
            _status("Bitte Grok's Antwort einfügen.")
        else:
            _status("Sandbox-Test läuft...", 0.4)
            neuer_code = st.session_state.geparster_code or _code_aus_antwort(str(antwort))
            ergebnis = zeitkapsel.sandbox_testen(
                st.session_state.geladenes_projekt,
                neuer_code,
                stein.get("datei", ""),
                stein=stein,
            )
            st.session_state.diff_status = ergebnis
            st.session_state.sandbox_ergebnis = ergebnis
            st.session_state.geparster_code = neuer_code
            _status(ergebnis.get("meldung", ""), 1.0 if ergebnis.get("erfolg") else 0.7)

    status = st.session_state.diff_status
    if status:
        _sandbox_details(status)
        if status.get("erfolg"):
            if st.button("Code übernehmen", type="primary", use_container_width=True):
                stein = _stein_finden(gewaehlt) if gewaehlt else None
                neuer_code = (
                    st.session_state.geparster_code
                    or _code_aus_antwort(st.session_state.get("grok_antwort", ""))
                )
                if not stein:
                    _status("Kein Legostein ausgewählt.")
                else:
                    ergebnis = zeitkapsel.code_uebernehmen(
                        st.session_state.geladenes_projekt,
                        neuer_code,
                        stein.get("datei", ""),
                        stein=stein,
                        anzahl_legosteine=len(st.session_state.legosteine),
                    )
                    st.session_state.code_uebernommen = ergebnis
                    _status(ergebnis.get("meldung", "Code übernommen."), 1.0)
                    _projekt_laden(st.session_state.geladenes_projekt, mit_backup=False)

    if st.session_state.code_uebernommen and st.session_state.code_uebernommen.get("erfolg"):
        st.success(st.session_state.code_uebernommen.get("meldung", "Code übernommen."))

    st.subheader("Diff-Anzeige")
    if status:
        hinzu = int(status.get("zeilen_hinzugefuegt") or 0)
        weg = int(status.get("zeilen_geloescht") or 0)
        st.caption(f"{hinzu} Zeilen hinzugefügt, {weg} Zeilen gelöscht. Grün = neu, rot = gelöscht.")
        diff_html = _diff_als_html(status.get("diff", ""))
        try:
            with st.container(height=420):
                st.markdown(diff_html, unsafe_allow_html=True)
        except TypeError:
            st.markdown(diff_html, unsafe_allow_html=True)
    else:
        st.caption("Noch kein Diff. Grün = neu, rot = gelöscht.")


def _fusszeile() -> None:
    st.markdown("---")
    links, mitte, rechts = st.columns([4, 3, 2])
    with links:
        text = st.session_state.fortschritt_text or st.session_state.statusmeldung or "Bereit."
        st.caption(text)
        st.progress(float(st.session_state.ki_fortschritt or 0.0), text=text)
    with mitte:
        panic = st.session_state.letzter_panic
        if panic:
            if panic.get("erfolg"):
                st.success(panic.get("meldung"))
            else:
                st.error(panic.get("meldung"))
            info = panic.get("backup_info") or {}
            if info:
                st.caption(
                    f"Wiederhergestellt: {info.get('projektname', '?')} · "
                    f"{info.get('anzahl_legosteine', '?')} Steine · "
                    f"{info.get('datum', '?')}"
                )
    with rechts:
        if st.button("🚨 PANIK", type="primary", use_container_width=True):
            st.session_state.panic_frage = True
        if st.session_state.panic_frage:
            st.warning("Bist du sicher? Diese Aktion setzt das gesamte Projekt zurück!")
            ja, nein = st.columns(2)
            with ja:
                if st.button("Ja, zurücksetzen", use_container_width=True):
                    pfad = st.session_state.geladenes_projekt
                    st.session_state.panic_frage = False
                    if not pfad:
                        st.session_state.letzter_panic = {
                            "erfolg": False,
                            "meldung": "Kein Projekt geladen – Panik-Knopf hat nichts zum Wiederherstellen.",
                            "backup_info": {},
                        }
                    else:
                        ergebnis = zeitkapsel.panik_knopf(pfad)
                        st.session_state.letzter_panic = ergebnis
                        if ergebnis.get("erfolg"):
                            _projekt_laden(pfad, mit_backup=False)
            with nein:
                if st.button("Nein, abbrechen", use_container_width=True):
                    st.session_state.panic_frage = False
                    _status("Panik-Aktion abgebrochen.")


def render(als_subapp: bool = False) -> None:
    """Zeichnet die Fabrik. Als Sub-App im Dashboard ohne set_page_config."""
    st.session_state["_fabrik_subapp"] = bool(als_subapp)
    if not als_subapp:
        st.set_page_config(
            page_title="Legostein-Fabrik v6.0",
            page_icon="🧱",
            layout="wide",
        )
        st.title("🧱 Legostein-Fabrik v6.0 Reality-Edition")
    else:
        st.markdown("### 🧱 Legostein-Fabrik v6.0 Reality-Edition")
    st.caption("AST-Scanner · Zeitmaschine · Sandbox · Grok-Prompt-Brücke")
    _session_vorbereiten()

    col1, col2, col3 = st.columns([3, 5, 2])
    with col1:
        _linke_spalte()
    with col2:
        _mittlere_spalte()
    with col3:
        _rechte_spalte()
    _fusszeile()


def main() -> None:
    render(als_subapp=False)


if __name__ == "__main__":
    main()
