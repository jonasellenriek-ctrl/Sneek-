"""Exakten Preis + Verfügbarkeit für die gesuchte Größe auf der Shop-Seite prüfen.

Google Shopping (und erst recht Marktplätze wie GOAT/StockX) zeigen oft nur den
günstigsten Preis über alle Größen. Hier wird die Produktseite selbst gelesen:

1. Shopify-Shops:   /products/<handle>.js  -> Varianten mit Größe, Preis, Bestand
2. Alle anderen:    schema.org-Daten (JSON-LD) der Seite -> Angebote je Größe

Ergebnis: "ok" (Größe lieferbar, exakter Preis), "sold_out" (Größe nicht
lieferbar) oder "unknown" (Seite gibt keine Größen-Preise preis).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from .http import HEADERS
from .matching import size_matches
from .models import Deal

log = logging.getLogger(__name__)

# Marktplätze/Vergleichsportale: Preise gelten nicht für eine bestimmte Größe
RESELLERS = [
    "goat", "stockx", "novelship", "lyst", "restocks", "klekt", "ebay", "resellzone", "resell",
    "kixify", "flight club", "flightclub", "stadium goods", "grailed", "vinted", "kleinanzeigen",
    "laced", "sneakerjagers", "sneakers123", "idealo", "farfetch", "kicks crew", "kickscrew",
    "hypeboost", "sole supplier", "solesupplier", "alias", "baselayer", "wethenew", "crepslocker",
]


def is_reseller(d: Deal) -> bool:
    text = f" {d.source} {urlparse(d.url).netloc} ".lower()
    return any(r in text for r in RESELLERS)


@dataclass
class Result:
    status: str                  # ok | sold_out | unknown
    price: float | None = None
    old_price: float | None = None
    size: str = ""
    how: str = ""


def _money(v) -> float | None:
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _shopify(url: str, aliases: list[str]) -> Result | None:
    p = urlparse(url)
    m = re.search(r"/products/([^/?#.]+)", p.path)
    if not m:
        return None
    try:
        r = requests.get(f"{p.scheme}://{p.netloc}/products/{m.group(1)}.js", headers=HEADERS, timeout=20)
        data = r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(data, dict) or "variants" not in data:
        return None
    hits = []
    for v in data["variants"]:
        labels = [str(v.get(k) or "") for k in ("option1", "option2", "option3", "title")]
        label = next((l for l in labels if size_matches(l, aliases)), None)
        if label is None:
            continue
        hits.append((bool(v.get("available")), (v.get("price") or 0) / 100,
                     (v.get("compare_at_price") or 0) / 100 or None, label))
    avail = [h for h in hits if h[0]]
    if avail:
        _, price, old, label = min(avail, key=lambda h: h[1])
        return Result("ok", price, old, label, "shopify")
    return Result("sold_out", how="shopify")


def _walk(node, out: list):
    """Alle Offer-artigen Knoten samt Größen-Label aus JSON-LD sammeln."""
    if isinstance(node, list):
        for n in node:
            _walk(n, out)
        return
    if not isinstance(node, dict):
        return
    t = str(node.get("@type", "")).lower()
    if "product" in t and "group" not in t:
        label = str(node.get("size") or "")
        offers = node.get("offers")
        offers = offers.get("offers", offers) if isinstance(offers, dict) else offers
        for o in offers if isinstance(offers, list) else [offers]:
            if isinstance(o, dict):
                lab = label or str(o.get("size") or (o.get("itemOffered") or {}).get("size") or o.get("name") or o.get("sku") or "")
                out.append((lab, _money(o.get("price") or o.get("lowPrice")), str(o.get("availability", ""))))
    for k in ("hasVariant", "@graph", "offers", "itemOffered", "mainEntity"):
        if k in node and k != "offers":
            _walk(node[k], out)


def _jsonld(url: str, title: str, aliases: list[str]) -> Result | None:
    try:
        r = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=25)
    except requests.RequestException:
        return None
    if not r.ok:
        log.info("  Prüfung %s: HTTP %s", urlparse(url).netloc, r.status_code)
        return None
    offers: list = []
    for block in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', r.text, re.S | re.I):
        try:
            _walk(json.loads(block.strip()), offers)
        except ValueError:
            continue
    # Nur Angebote mit echtem Größen-Label zählen (Modellname rausnehmen, z. B. "LeBron 16")
    labelled = []
    t = title.lower()
    for lab, price, av in offers:
        clean = lab.lower().replace(t, " ") if t else lab.lower()
        if clean.strip():
            labelled.append((clean, price, av))
    sized = [o for o in labelled if size_matches(o[0], aliases)]
    if not sized:
        # Seite listet Größen, aber nicht unsere -> nicht lieferbar; sonst unbekannt
        return Result("sold_out", how="json-ld") if len(labelled) >= 4 else None
    avail = [o for o in sized if "instock" in o[2].lower().replace(" ", "") or "limitedavailability" in o[2].lower()]
    if avail:
        lab, price, _ = min(avail, key=lambda o: o[1] or 1e9)
        return Result("ok", price, None, lab.strip(), "json-ld")
    return Result("sold_out", how="json-ld")


def verify(d: Deal, aliases: list[str]) -> Result:
    if "google." in urlparse(d.url).netloc:
        return Result("unknown", how="kein Direktlink")
    res = _shopify(d.url, aliases) or _jsonld(d.url, d.title, aliases)
    return res or Result("unknown", how="keine Größen-Daten")
