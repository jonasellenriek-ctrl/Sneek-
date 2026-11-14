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
            # stabiler Schlüssel, damit sich "schon gesehen" nicht ändert, wenn der Link aufgelöst wird
            extra={"key": f"google|{r.get('source', '?')}|{title}",
                   "gtoken": r.get("immersive_product_page_token") or ""},
        ))
    return deals


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def store_link(data: dict, source: str) -> str:
    """Aus der Google-Produktseite den Link des Shops holen, der den Deal hat."""
    stores = ((data or {}).get("product_results") or {}).get("stores") or []
    want = _norm(source)
    best = ""
    for st in stores:
        link = st.get("link") or ""
        if not link.startswith("http") or "google." in urlparse(link).netloc:
            continue
        name = _norm(st.get("name", ""))
        if want and name and (want in name or name in want):
            return link
        best = best or link
    return best


def resolve_links(deals: list[Deal], cache: dict, limit: int) -> int:
    """Ersetzt Google-Links durch direkte Shop-Links (1 SerpAPI-Abfrage je Schuh,
    Ergebnis wird gemerkt). Gibt die Zahl der Abfragen zurück."""
    key = env("SERPAPI_KEY")
    used = 0
    for d in deals:
        if "google." not in urlparse(d.url).netloc:
            continue
        if d.key in cache:
            d.url = cache[d.key]
            continue
        if not key or used >= limit:
            continue
        if not d.extra.get("gtoken"):
            log.info("Direktlink: kein Produkt-Token für %s (%s)", d.title, d.source)
            continue
        used += 1
        data = get_json(API, params={"engine": "google_immersive_product",
                                     "page_token": d.extra["gtoken"], "api_key": key})
        link = store_link(data, d.source.removeprefix("google:"))
        if not link:
            stores = ((data or {}).get("product_results") or {}).get("stores") or []
            log.info("Direktlink: nichts gefunden für %s (Antwort: %s, %d Shops)",
                     d.title, sorted((data or {}).keys())[:8], len(stores))
        if link:
            d.url = cache[d.key] = link
            log.info("Direktlink: %s -> %s", d.title, urlparse(link).netloc)
    return used


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
