"""Bewertet jeden Deal von 1–10 in mehreren Kategorien.

Kategorien:
  Rabatt  – wie stark reduziert (70 % = 10)
  Preis   – absoluter Preis (≤ 60 = 10, ≥ 200 = 2)
  Modell  – Performance + Beliebtheit der Modellreihe (Kobe = 10)
  Größe   – US 16 im Shop bestätigt (10) oder nur vermutet (5)
  Shop    – Vertrauenswürdigkeit des Händlers
"""
from __future__ import annotations

from urllib.parse import urlparse

from .models import Deal

# Performance/Hype der Modellreihen, 1–10 (erste passende Zeile gewinnt)
MODEL_SCORES: list[tuple[str, int]] = [
    ("kobe", 10), ("mamba", 10),
    ("gt cut", 9), ("g.t. cut", 9), ("sabrina", 9), ("ae 1", 9), ("anthony edwards", 9),
    ("book 1", 8), ("luka", 8), ("lebron", 8), ("curry", 8), ("tatum", 8), ("way of wade", 8),
    ("gt hustle", 8), ("ja 1", 8), ("ja 2", 8), ("ja 3", 8),
    (" kd", 7), ("giannis", 7), ("freak", 7), ("mb.0", 7), ("lamelo", 7), ("dame", 7),
    ("zion", 7), ("gt jump", 7), ("trae young", 7),
    ("harden", 6), ("air jordan", 6), ("jordan", 6),
]

TRUSTED_SHOPS: list[tuple[str, int]] = [
    ("nike", 10), ("adidas", 10), ("puma", 9), ("zalando", 9), ("about you", 9), ("aboutyou", 9),
    ("snipes", 9), ("foot locker", 9), ("footlocker", 9), ("kickz", 9), ("jd sports", 9),
    ("bstn", 9), ("43einhalb", 9), ("solebox", 9), ("sportscheck", 8), ("end.", 9), ("size?", 9),
    ("shoepalace", 8), ("dtlr", 8), ("kith", 9), ("undefeated", 9), ("overkill", 9), ("cncpts", 9),
    ("otto", 8), ("amazon", 7), ("zalando lounge", 9), ("bestsecret", 9),
    ("ebay", 4), ("stockx", 7), ("goat", 7), ("klekt", 7),
]


def _clamp(x: float) -> float:
    return max(1.0, min(10.0, x))


def model_score(title: str) -> int:
    t = f" {title.lower()} "
    for key, score in MODEL_SCORES:
        if key in t:
            return score
    return 5


def shop_score(d: Deal) -> int:
    text = f"{d.source} {urlparse(d.url).netloc}".lower()
    for key, score in TRUSTED_SHOPS:
        if key in text:
            return score
    return 8 if d.source.startswith("shopify:") else 5


def rate(d: Deal, weights: dict | None = None) -> dict:
    w = weights or {"rabatt": .3, "preis": .2, "modell": .25, "groesse": .15, "shop": .1}
    pct = d.discount_percent or (d.extra.get("max_pct") or 0)
    scores = {
        "rabatt": _clamp(pct / 7),
        "preis": _clamp(10 - (d.price - 60) / 140 * 8) if d.price else 5.0,
        "modell": float(model_score(d.title)),
        "groesse": 10.0 if d.size_verified else 5.0,
        "shop": float(shop_score(d)),
    }
    total = sum(scores[k] * w.get(k, 0) for k in scores) / (sum(w.values()) or 1)
    return {"gesamt": round(total, 1), **{k: round(v, 1) for k, v in scores.items()}}


LABELS = {"rabatt": "Rabatt", "preis": "Preis", "modell": "Modell", "groesse": "Größe", "shop": "Shop"}
