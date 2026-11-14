"""Google Shopping (über SerpAPI) – deckt praktisch alle Online-Shops ab:
Zalando, About You, Snipes, Foot Locker, Nike, adidas, Kickz, Amazon, eBay usw.

Google liefert Preis und Streichpreis, aber nicht zuverlässig die Größe.
Treffer werden deshalb mit "Größe bitte prüfen" gemeldet.
"""
from __future__ import annotations

import logging

from urllib.parse import parse_qs, urlparse

from ..http import env, get_json
from ..matching import is_basketball
from ..models import Deal

log = logging.getLogger(__name__)
API = "https://serpapi.com/search.json"


def direct_link(r: dict) -> str:
    """Möglichst den direkten Link zum Shop statt zur Google-Produktseite."""
    candidates = [r.get("link"), r.get("product_link")]
    for u in candidates:
        if not u:
            continue
        p = urlparse(u)
        if "google." not in p.netloc:
            return u
        q = parse_qs(p.query)
        for k in ("adurl", "url", "q"):
            target = (q.get(k) or [""])[0]
            if target.startswith("http") and "google." not in urlparse(target).netloc:
                return target
    return r.get("product_link") or r.get("link") or ""


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
            url=direct_link(r),
            currency="€",
            image=r.get("thumbnail", "") if str(r.get("thumbnail", "")).startswith("http") else "",
            price=float(price),
            old_price=float(old),
            note=f"Gefunden über Google Shopping bei {r.get('source', '?')}",
        ))
    return deals


def search(cfg: dict) -> list[Deal]:
    key = env("SERPAPI_KEY")
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
        for d in found:
            log.info("  %s -> %s", d.source, urlparse(d.url).netloc)
        log.info("Google Shopping '%s': %d reduzierte Treffer", q, len(found))
        deals.extend(found)
    return deals
