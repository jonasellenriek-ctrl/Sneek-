"""Google Shopping (über SerpAPI) – deckt praktisch alle Online-Shops ab:
Zalando, About You, Snipes, Foot Locker, Nike, adidas, Kickz, Amazon, eBay usw.

Google liefert Preis und Streichpreis, aber nicht zuverlässig die Größe.
Treffer werden deshalb mit "Größe bitte prüfen" gemeldet.
"""
from __future__ import annotations

import logging
import os

from ..http import get_json
from ..matching import is_basketball
from ..models import Deal

log = logging.getLogger(__name__)
API = "https://serpapi.com/search.json"


def deals_from_results(results: list[dict], cfg: dict) -> list[Deal]:
    deals = []
    for r in results:
        title = r.get("title", "")
        if not is_basketball(title + " basketball", cfg["basketball_keywords"], cfg["exclude_keywords"]):
            continue
        price = r.get("extracted_price")
        old = r.get("extracted_old_price")
        if price is None or old is None:
            continue
        deals.append(Deal(
            source=f"google:{r.get('source', '?')}",
            title=title,
            url=r.get("product_link") or r.get("link") or "",
            price=float(price),
            old_price=float(old),
            note=f"Gefunden über Google Shopping bei {r.get('source', '?')}",
        ))
    return deals


def search(cfg: dict) -> list[Deal]:
    key = os.environ.get("SERPAPI_KEY")
    if not key:
        log.info("Google Shopping übersprungen (kein SERPAPI_KEY gesetzt)")
        return []
    gcfg = cfg["sources"]["google_shopping"]
    deals: list[Deal] = []
    for q in gcfg.get("queries", []):
        data = get_json(API, params={
            "engine": "google_shopping", "q": q, "api_key": key,
            "gl": gcfg.get("country", "de"), "hl": gcfg.get("language", "de"),
            "num": 100,
        })
        if not data:
            continue
        results = (data.get("shopping_results") or []) + (data.get("inline_shopping_results") or [])
        found = deals_from_results(results, cfg)
        log.info("Google Shopping '%s': %d reduzierte Treffer", q, len(found))
        deals.extend(found)
    return deals
