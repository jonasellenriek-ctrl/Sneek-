"""Shopify-Shops über die öffentliche /products.json-Schnittstelle durchsuchen."""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from ..http import get_json
from ..matching import is_basketball, size_matches
from ..models import Deal

log = logging.getLogger(__name__)


def _size_option_index(product: dict) -> int | None:
    for i, opt in enumerate(product.get("options") or []):
        name = str(opt.get("name", "") if isinstance(opt, dict) else opt).lower()
        if any(w in name for w in ("size", "größe", "grösse", "taille", "us")):
            return i + 1
    return None


def _sized(url: str, width: int = 600) -> str:
    """Shopify-CDN liefert kleinere Bilder über ?width=…"""
    if not url:
        return ""
    url = "https:" + url if url.startswith("//") else url
    return url + ("&" if "?" in url else "?") + f"width={width}"


def deals_from_products(products: list[dict], shop: str, cfg: dict) -> list[Deal]:
    deals: list[Deal] = []
    host = urlparse(shop).netloc.removeprefix("www.")
    for p in products:
        text = " ".join([
            p.get("title", ""), p.get("product_type", "") or "", p.get("vendor", "") or "",
            " ".join(p.get("tags") or []) if isinstance(p.get("tags"), list) else str(p.get("tags", "")),
        ])
        if not is_basketball(text, cfg["basketball_keywords"], cfg["exclude_keywords"]):
            continue
        size_idx = _size_option_index(p)
        imgs = p.get("images") or []
        image = (imgs[0].get("src", "") if imgs and isinstance(imgs[0], dict) else "")
        for v in p.get("variants") or []:
            if not v.get("available", False):
                continue
            if size_idx:
                size_val = str(v.get(f"option{size_idx}") or "")
            else:
                size_val = str(v.get("title") or "")
            if not size_matches(size_val, cfg["size_aliases"]):
                continue
            try:
                price = float(v.get("price") or 0)
                old = float(v.get("compare_at_price") or 0) or None
            except (TypeError, ValueError):
                continue
            deals.append(Deal(
                source=f"shopify:{host}",
                title=p.get("title", "?"),
                url=f"{shop.rstrip('/')}/products/{p.get('handle')}?variant={v.get('id')}",
                price=price,
                old_price=old,
                size=size_val,
                size_verified=True,
                image=_sized(image),
            ))
    return deals


def search(cfg: dict) -> list[Deal]:
    scfg = cfg["sources"]["shopify"]
    all_deals: list[Deal] = []
    for shop in scfg.get("shops", []):
        found = 0
        for page in range(1, int(scfg.get("max_pages", 8)) + 1):
            data = get_json(f"{shop.rstrip('/')}/products.json", params={"limit": 250, "page": page})
            if not data or not data.get("products"):
                break
            deals = deals_from_products(data["products"], shop, cfg)
            found += len(deals)
            all_deals.extend(deals)
            if len(data["products"]) < 250:
                break
        log.info("Shopify %s: %d Treffer in US 16", shop, found)
    return all_deals
