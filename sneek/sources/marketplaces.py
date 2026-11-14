"""StockX mit exaktem Preis für US 16 – über die pckt.sh-API.

Ablauf (jede Anfrage kostet 1 Credit, Gratis-Plan: 500 Credits/Monat):
  1. /v1/stockx/search?query=…   -> Produkte inkl. Liste der Größen (ohne Größen-Preise)
  2. /v1/stockx/asks?id=<urlKey> -> alle Angebote je Größe; daraus das günstigste in US 16

Nur Produkte, die US 16 überhaupt führen, werden in Schritt 2 abgefragt –
Kobe zuerst, höchstens `max_price_checks` pro Lauf.

Die Preise kommen vom US-Markt von StockX (US-Dollar), zzgl. Gebühren/Versand/Zoll.
Braucht den Secret KICKSDB_API_KEY (pckt.sh-Key, beginnt mit "pkt_").
"""
from __future__ import annotations

import logging
import time

import requests

from ..http import ERRORS, HEADERS, env
from ..matching import contains_any, is_basketball
from ..models import Deal

log = logging.getLogger(__name__)
API = "https://api.pckt.sh/v1"


_last_call = 0.0


def _get(path: str, params: dict, key: str) -> dict:
    """GET mit Pause: der Gratis-Plan erlaubt 1 Anfrage pro Sekunde (sonst HTTP 426/429)."""
    global _last_call
    r = None
    for attempt in range(3):
        wait = 1.2 - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(f"{API}{path}", params=params, timeout=25,
                             headers={**HEADERS, "Accept": "application/json", "Authorization": f"Bearer {key}"})
        except requests.RequestException as e:
            ERRORS.append(f"StockX (pckt.sh): {type(e).__name__}")
            return {}
        finally:
            _last_call = time.monotonic()
        if r.status_code not in (426, 429):
            break
        time.sleep(2 * (attempt + 1))
    if r.status_code != 200:
        msg = {401: "API-Key ungültig", 402: "Credits aufgebraucht", 426: "zu viele Anfragen", 429: "Limit erreicht"}.get(
            r.status_code, f"HTTP {r.status_code}")
        log.warning("pckt.sh %s -> %s", path, msg)
        if not any(e.startswith("StockX") for e in ERRORS):
            ERRORS.append(f"StockX (pckt.sh): {msg}")
        return {}
    try:
        return r.json() or {}
    except ValueError:
        return {}


def products_from_search(data: dict) -> list[dict]:
    edges = (((data.get("data") or {}).get("browse") or {}).get("results") or {}).get("edges") or []
    return [e.get("node") or {} for e in edges]


def has_size(node: dict, size: str) -> bool:
    for v in node.get("variants") or []:
        sc = v.get("sizeChart") or {}
        if str((v.get("traits") or {}).get("size")) == size and str(sc.get("baseType", "us m")).lower() == "us m":
            return True
    return False


def size_prices(data: dict, size: str) -> tuple[float | None, list[float]]:
    """(günstigstes Angebot in `size`, günstigstes Angebot je anderer Größe)."""
    variants = ((data.get("data") or {}).get("product") or {}).get("variants") or []
    mine, others = None, []
    for v in variants:
        if v.get("hidden"):
            continue
        levels = (((v.get("market") or {}).get("priceLevels") or {}).get("edges")) or []
        amounts = []
        for e in levels:
            try:
                amounts.append(float((e.get("node") or {}).get("amount")))
            except (TypeError, ValueError):
                continue
        if not amounts:
            continue
        base_type = str((v.get("sizeChart") or {}).get("baseType", "us m")).lower()
        if str((v.get("traits") or {}).get("size")) == size and base_type == "us m":
            mine = min(amounts) if mine is None else min(mine, min(amounts))
        else:
            others.append(min(amounts))
    return mine, others


def search(cfg: dict) -> list[Deal]:
    key = env("PCKT_API_KEY") or env("KICKSDB_API_KEY")
    if not key:
        log.info("StockX übersprungen (kein KICKSDB_API_KEY gesetzt)")
        return []
    mcfg = cfg["sources"]["marketplaces"]
    size = str(mcfg.get("us_size", "16"))
    focus_kw = (cfg.get("focus") or {}).get("keywords", [])

    # 1. Suchen
    candidates: dict[str, dict] = {}
    for q in mcfg.get("queries", []):
        nodes = products_from_search(_get("/stockx/search", {"query": q}, key))
        ok = [n for n in nodes
              if n.get("urlKey") and has_size(n, size)
              and is_basketball(f"{n.get('title', '')} basketball", cfg["basketball_keywords"], cfg["exclude_keywords"])
              and "opened packaging" not in n.get("title", "").lower()]
        for n in ok:
            candidates.setdefault(n["urlKey"], n)
        log.info("StockX-Suche '%s': %d Produkte, %d führen US %s", q, len(nodes), len(ok), size)

    # 2. Größen-Preise holen – Kobe zuerst, dann nach Beliebtheit (Verkäufe der letzten 72 h)
    def prio(n: dict):
        sales = (((n.get("market") or {}).get("salesInformation") or {}).get("salesLast72Hours")) or 0
        return (not contains_any(n.get("title", ""), focus_kw), -sales)

    deals: list[Deal] = []
    for n in sorted(candidates.values(), key=prio)[: int(mcfg.get("max_price_checks", 10))]:
        price, others = size_prices(_get("/stockx/asks", {"id": n["urlKey"]}, key), size)
        if price is None:
            log.info("  %s: kein Angebot in US %s", n.get("title"), size)
            continue
        avg = sum(others) / len(others) if others else None
        log.info("  %s: US %s ab %.0f $ (Ø andere Größen %s)", n.get("title"), size, price,
                 f"{avg:.0f} $" if avg else "–")
        deals.append(Deal(
            source="StockX", title=n.get("title") or "", url=f"https://stockx.com/{n['urlKey']}",
            price=price, old_price=avg, currency="$", size=f"US {size}", size_verified=True,
            image=((n.get("media") or {}).get("thumbUrl")) or "",
            note="StockX-Angebot genau in US 16 (US-Markt, Dollar) · Vergleich: Ø-Preis der anderen Größen"
                 " · zzgl. Gebühren, Versand und ggf. Zoll",
            extra={"key": f"stockx|{n['urlKey']}|{size}", "market": True,
                   "min_pct": mcfg.get("min_discount_percent", 15),
                   "max_ok_price": mcfg.get("always_show_below", None)},
        ))
    return deals
