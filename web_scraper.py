# -*- coding: utf-8 -*-
"""
Code_Maker_Matrix (CMM) – Web-Scraper

(c) 2026 Christian Schmitt, Solingen, Germany
Email: c.schmitt@me.com
Tel.: 015204006286

Alle Rechte vorbehalten.
"""

from __future__ import annotations


def scrape_webseite(url: str, max_length: int = 8000) -> dict:
    """Ruft Webseiten-Inhalt ab und bereitet ihn für die KI auf."""
    try:
        import requests
        from bs4 import BeautifulSoup
    except ImportError:
        return {
            "erfolg": False,
            "fehler": "requests oder beautifulsoup4 nicht installiert. Bitte: pip install requests beautifulsoup4",
        }

    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        zeilen = [z.strip() for z in text.splitlines() if z.strip()]
        text = "\n".join(zeilen)
        if len(text) > max_length:
            text = text[:max_length] + "\n\n[...]"
        titel = url
        if soup.title and soup.title.string:
            titel = soup.title.string.strip()
        return {
            "erfolg": True,
            "url": url,
            "titel": titel,
            "text": text,
            "laenge": len(text),
        }
    except Exception as e:
        return {"erfolg": False, "fehler": str(e), "url": url}
