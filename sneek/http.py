from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def get_json(url: str, params: dict | None = None, retries: int = 2, timeout: int = 25):
    """GET mit Wiederholungen. Gibt None zurück statt Fehler zu werfen,
    damit ein einzelner kaputter Shop nicht den ganzen Lauf stoppt."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 429 and attempt < retries:
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code != 200:
                log.warning("%s -> HTTP %s", url, r.status_code)
                return None
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            log.warning("%s -> %s", url, e)
    return None
