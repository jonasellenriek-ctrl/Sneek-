"""Zalando Lounge über das eigene E-Mail-Postfach überwachen.

Zalando Lounge ist nur eingeloggt sichtbar und verbietet automatisiertes
Auslesen. Jede neue Aktion wird aber per Newsletter angekündigt. Der Bot liest
diese Mails (IMAP, z. B. GMX: imap.gmx.net) und meldet Aktionen mit passenden
Marken/Stichwörtern. Die Größe 16 muss man dann in der Aktion selbst prüfen.
"""
from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from html import unescape

from ..matching import contains_any
from ..models import Deal

log = logging.getLogger(__name__)


def _text(msg: email.message.Message) -> str:
    parts = []
    for part in msg.walk():
        if part.get_content_type() in ("text/plain", "text/html"):
            try:
                payload = part.get_payload(decode=True) or b""
                parts.append(payload.decode(part.get_content_charset() or "utf-8", "replace"))
            except Exception:  # noqa: BLE001 – kaputte Mails einfach überspringen
                continue
    return "\n".join(parts)


def deal_from_message(msg: email.message.Message, mcfg: dict) -> Deal | None:
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    body = _text(msg)
    plain = unescape(re.sub(r"<[^>]+>", " ", body))
    if not contains_any(f"{subject} {plain}", mcfg.get("keywords", [])):
        return None
    pct = [int(x) for x in re.findall(r"(?:bis zu\s*)?-\s?(\d{2})\s?%", plain)]
    links = re.findall(r'https?://[^\s"\'<>]*zalando-lounge[^\s"\'<>]*', body)
    return Deal(
        source="zalando-lounge (Mail)",
        title=subject or "Neue Zalando-Lounge-Aktion",
        url=links[0] if links else "https://www.zalando-lounge.de/",
        note=(f"Aktion bis zu -{max(pct)}%. " if pct else "") + "Größe US 16 / EU 50.5 in der Aktion prüfen.",
        extra={"max_pct": max(pct) if pct else None,
               "key": "lounge|" + (msg.get("Message-ID") or subject)},
    )


def search(cfg: dict) -> list[Deal]:
    host, user, pw = (os.environ.get(k) for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"))
    if not (host and user and pw):
        log.info("Zalando-Lounge-Mails übersprungen (IMAP_HOST/IMAP_USER/IMAP_PASSWORD fehlen)")
        return []
    mcfg = cfg["sources"]["zalando_lounge_mail"]
    since = (datetime.now() - timedelta(days=int(mcfg.get("lookback_days", 3)))).strftime("%d-%b-%Y")
    deals: list[Deal] = []
    try:
        with imaplib.IMAP4_SSL(host) as imap:
            imap.login(user, pw)
            imap.select("INBOX", readonly=True)
            _, data = imap.search(None, "SINCE", since, "FROM", f'"{mcfg.get("sender_contains", "zalando-lounge")}"')
            for num in data[0].split():
                _, raw = imap.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(raw[0][1])
                d = deal_from_message(msg, mcfg)
                if d:
                    deals.append(d)
    except (imaplib.IMAP4.error, OSError) as e:
        log.warning("IMAP-Fehler: %s", e)
    log.info("Zalando Lounge: %d passende Aktionen", len(deals))
    return deals
