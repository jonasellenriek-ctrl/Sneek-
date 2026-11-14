"""Ein Suchlauf: alle Quellen abfragen, filtern und den Tages-Report mailen.

Start:  python -m sneek.main                  (normal)
        python -m sneek.main --dry-run        (nichts senden, State nicht speichern)
        python -m sneek.main --preview r.html (Report zusätzlich als HTML-Datei speichern)
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import yaml

from . import http, notify
from .models import Deal
from .sources import google_shopping, newsletter_mail, shopify

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("sneek")


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {"seen": {}, "last_run": {}}


def is_good_deal(d: Deal, cfg: dict) -> bool:
    if d.extra.get("club"):
        return True  # Aktionen ohne Einzelpreis – Stichwortfilter reicht
    pct = d.discount_percent
    if pct is None or pct < cfg["min_discount_percent"]:
        return False
    if cfg.get("max_price") is not None and d.price is not None and d.price > cfg["max_price"]:
        return False
    return True


def select_new(deals: list[Deal], state: dict) -> list[Deal]:
    """Nur melden, was neu ist oder seit der letzten Meldung billiger wurde."""
    new, seen = [], state.setdefault("seen", {})
    for d in deals:
        prev = seen.get(d.key)
        if prev is None or (d.price is not None and prev.get("price") is not None and d.price < prev["price"] - 0.01):
            new.append(d)
        seen[d.key] = {"price": d.price, "ts": int(time.time())}
    # Einträge älter als 60 Tage vergessen, damit die Datei klein bleibt
    cutoff = time.time() - 60 * 86400
    state["seen"] = {k: v for k, v in seen.items() if v.get("ts", 0) >= cutoff}
    return new


def due(name: str, hours: float, state: dict) -> bool:
    last = state.setdefault("last_run", {}).get(name, 0)
    return time.time() - last >= hours * 3600


def run(cfg: dict, state: dict) -> tuple[list[Deal], list[Deal]]:
    """Gibt (alle guten Deals, davon neue) zurück."""
    sources = cfg["sources"]
    deals: list[Deal] = []
    if sources.get("shopify", {}).get("enabled"):
        deals += shopify.search(cfg)
    gs = sources.get("google_shopping", {})
    if gs.get("enabled") and due("google_shopping", gs.get("min_interval_hours", 12), state):
        deals += google_shopping.search(cfg)
        state["last_run"]["google_shopping"] = int(time.time())
    if sources.get("newsletter_mail", {}).get("enabled"):
        deals += newsletter_mail.search(cfg)

    good = [d for d in deals if is_good_deal(d, cfg)]
    good.sort(key=lambda d: -(d.discount_percent or 0))
    # Doppelte (gleicher Shop/Link/Größe) zusammenfassen
    unique = list({d.key: d for d in good}.values())
    log.info("%d Treffer insgesamt, %d gute Deals", len(deals), len(unique))
    return unique, select_new(unique, state)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    ap.add_argument("--state", default=str(ROOT / "state" / "seen.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--preview", help="Report zusätzlich als HTML-Datei speichern")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = yaml.safe_load(Path(args.config).read_text())
    state_path = Path(args.state)
    state = load_state(state_path)
    deals, new = run(cfg, state)
    log.info("%d neue Deals", len(new))

    subject, html = notify.build_report(deals, new, http.ERRORS, cfg)
    if args.preview:
        Path(args.preview).write_text(html)
    if args.dry_run:
        print(subject)
        for d in deals:
            print("\n" + d.format())
        return
    if deals or cfg.get("report", {}).get("send_empty", True):
        notify.send_email(subject, html)
    notify.telegram(new)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
