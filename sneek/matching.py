"""Größen- und Produkt-Erkennung."""
from __future__ import annotations

import re


def _norm(s: str) -> str:
    s = s.lower().replace(",", ".").replace("½", ".5").replace("⅓", " 1/3")
    return re.sub(r"\s+", " ", s).strip()


def size_matches(value: str, aliases: list[str]) -> bool:
    """True, wenn eine Größenangabe einem der Aliase entspricht.

    Ein Alias muss als ganzes "Token" vorkommen, damit z. B. "16" nicht
    auf "16.5", "116" oder "EU 41 / US 8 / 16cm" ... fälschlich passt.
    Varianten wie "Black / 16" oder "US 16 | EU 50.5" werden erkannt.
    """
    v = _norm(value)
    for alias in aliases:
        a = _norm(alias)
        # davor: Anfang oder Nicht-Ziffer/Punkt; danach: Ende oder kein Ziffer/Punkt/Bruch
        pattern = r"(?<![\d.])" + re.escape(a) + r"(?![\d]|\.\d|\s?1/[23]|\s?2/3|\s?cm)"
        if re.search(pattern, v):
            # Reines "16" darf nicht Teil einer EU-/cm-Angabe sein, z. B. "EU 16" (Kinder)
            if a.isdigit() and re.search(r"(eu|cm|uk)\s?" + re.escape(a) + r"(?![\d.])", v):
                continue
            return True
    return False


def contains_any(text: str, keywords: list[str]) -> bool:
    t = f" {text.lower()} "
    return any(k.lower() in t for k in keywords)


def is_basketball(text: str, keywords: list[str], exclude: list[str]) -> bool:
    t = text.lower()
    if contains_any(t, exclude):
        return False
    return contains_any(t, keywords)
