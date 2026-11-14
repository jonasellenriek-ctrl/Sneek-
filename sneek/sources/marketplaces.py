"""StockX und GOAT über die KicksDB-API (offizielle Daten-Schnittstelle).

Anders als bei Google Shopping kommt hier der exakte Preis je Größe:
  StockX: Markt DE (EUR), Variante mit size_type "us m" und size "16"
  GOAT:   Markt NL (EUR), Variante mit size "16" und available = true

Vergleichspreis für den "Rabatt": UVP, falls bekannt (GOAT retail_prices),
sonst der Durchschnittspreis des Modells über alle Größen (StockX avg_price).
Braucht den Secret KICKSDB_API_KEY.  Doku: https://docs.kicks.dev
"""
from __future__ import annotations

import logging
import re

import requests

from ..http import ERRORS, HEADERS, env
from ..matching import is_basketball
from ..models import Deal

log = logging.getLogger(__name__)
API = "https://api.kicks.dev/v3"


def _get(path: str, params: dict, key: str) -> list[dict]:
    try:
        r = requests.get(f"{API}{path}", params=params, timeout=20,
                         headers={**HEADERS, "Accept": "application/json", "Authorization": f"Bearer {key}"})
    except requests.RequestException as e:
        ERRORS.append(f"KicksDB: {type(e).__name__}")
        return []
    quota = r.headers.get("X-Quota-Current")
    if quota:
        log.info("KicksDB-Kontingent diesen Monat verbraucht: %s Anfragen", quota)
    if r.status_code != 200:
        msg = {401: "API-Key ungültig", 429: "Limit erreicht"}.get(r.status_code, f"HTTP {r.status_code}")
        log.warning("KicksDB %s -> %s", path, msg)
        if not any(e.startswith("KicksDB") for e in ERRORS):
            ERRORS.append(f"KicksDB: {msg}")
        return []
    try:
        data = r.json().get("data") or []
    except ValueError:
        return []
    return data if isinstance(data, list) else [data]


def _num(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:[.,]\d+)?", str(v or ""))
    return float(m.group().replace(",", ".")) if m else None


def _retail(p: dict) -> float | None:
    rp = p.get("retail_prices")
    if isinstance(rp, dict):
        for k in ("EUR", "eur", "NL", "DE", "EU"):
            if rp.get(k):
                return _num(rp[k])
    return None


def stockx_deals(products: list[dict], size: str, cfg: dict) -> list[Deal]:
    deals = []
    for p in products:
        title = p.get("title") or ""
        text = f"{title} {p.get('model', '')} {p.get('category', '')} {p.get('secondary_category', '')}"
        if not is_basketball(text + " basketball", cfg["basketball_keywords"], cfg["exclude_keywords"]):
            continue
        for v in p.get("variants") or []:
            if str(v.get("size")) != size or not str(v.get("size_type", "")).lower().startswith("us m"):
                continue
            ask = _num(v.get("lowest_ask"))
            if not ask or (v.get("total_asks") == 0):
                continue
            ref = _num(p.get("avg_price"))
            deals.append(Deal(
                source="StockX", title=title, url=p.get("link") or "", price=ask, old_price=ref,
                currency="€", size=f"US {size}", size_verified=True, image=p.get("image") or "",
                note="Vergleich: Ø-Preis aller Größen auf StockX · Preis zzgl. StockX-Gebühren/Versand",
                extra={"key": f"stockx|{p.get('id')}|{size}", "market": True},
            ))
    return deals


def goat_deals(products: list[dict], size: str, cfg: dict) -> list[Deal]:
    deals = []
    for p in products:
        title = p.get("name") or ""
        text = f"{title} {p.get('model', '')} {p.get('brand', '')}"
        if not is_basketball(text + " basketball", cfg["basketball_keywords"], cfg["exclude_keywords"]):
            continue
        asks = [_num(v.get("lowest_ask")) for v in p.get("variants") or []
                if str(v.get("size")) == size and v.get("available")]
        asks = [a for a in asks if a]
        if not asks:
            continue
        retail = _retail(p)
        all_asks = [_num(v.get("lowest_ask")) for v in p.get("variants") or [] if v.get("available")]
        all_asks = [a for a in all_asks if a]
        ref = retail or (sum(all_asks) / len(all_asks) if all_asks else None)
        deals.append(Deal(
            source="GOAT", title=title, url=p.get("link") or "", price=min(asks), old_price=ref,
            currency="€", size=f"US {size}", size_verified=True, image=p.get("image_url") or "",
            note=("Vergleich: UVP" if retail else "Vergleich: Ø-Preis aller Größen auf GOAT")
                 + " · Preis zzgl. GOAT-Gebühren/Versand",
            extra={"key": f"goat|{p.get('id')}|{size}", "market": True},
        ))
    return deals


def search(cfg: dict) -> list[Deal]:
    key = env("KICKSDB_API_KEY")
    if not key:
        log.info("StockX/GOAT übersprungen (kein KICKSDB_API_KEY gesetzt)")
        return []
    mcfg = cfg["sources"]["marketplaces"]
    size = str(mcfg.get("us_size", "16"))
    deals: list[Deal] = []
    for q in mcfg.get("queries", []):
        if "stockx" in mcfg.get("platforms", ["stockx", "goat"]):
            data = _get("/stockx/products", {"query": q, "limit": 20, "market": mcfg.get("stockx_market", "DE"),
                                             "display[variants]": "true"}, key)
            found = stockx_deals(data, size, cfg)
            deals += found
            log.info("StockX '%s': %d Modelle, %d in US %s", q, len(data), len(found), size)
        if "goat" in mcfg.get("platforms", ["stockx", "goat"]):
            data = _get("/goat/products", {"query": q, "limit": 20, "market": mcfg.get("goat_market", "NL"),
                                           "display[variants]": "true"}, key)
            found = goat_deals(data, size, cfg)
            deals += found
            log.info("GOAT '%s': %d Modelle, %d in US %s", q, len(data), len(found), size)
    for d in deals:
        d.extra["min_pct"] = mcfg.get("min_discount_percent", 15)
    return deals
