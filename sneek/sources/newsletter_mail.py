"""Shopping-Clubs (Zalando Lounge, BestSecret, ...) über das eigene Postfach überwachen.

Diese Shops sind nur eingeloggt sichtbar und verbieten automatisiertes Auslesen.
Jede neue Aktion wird aber per Newsletter angekündigt. Der Bot liest diese Mails
nur lesend (IMAP, z. B. GMX: imap.gmx.net) und meldet Aktionen mit passenden
Marken/Stichwörtern. Größe 16 muss man dann in der Aktion selbst prüfen.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header, make_header
from html import unescape

from ..http import ERRORS, env
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


def deal_from_message(msg: email.message.Message, club: dict, keywords: list[str]) -> Deal | None:
    subject = str(make_header(decode_header(msg.get("Subject", ""))))
    body = _text(msg)
    plain = unescape(re.sub(r"<[^>]+>", " ", body))
    if not contains_any(f"{subject} {plain}", keywords):
        return None
    pct = [int(x) for x in re.findall(r"-\s?(\d{2})\s?%", plain)]
    domain = club.get("link_contains") or club["sender_contains"]
    links = re.findall(r'https?://[^\s"\'<>]*' + re.escape(domain) + r'[^\s"\'<>]*', body)
    return Deal(
        source=f"{club['name']} (Newsletter)",
        title=subject or f"Neue {club['name']}-Aktion",
        url=links[0] if links else club.get("url", ""),
        note=(f"Aktion bis zu -{max(pct)}%. " if pct else "") + "Größe US 16 / EU 50.5 in der Aktion prüfen.",
        extra={"max_pct": max(pct) if pct else None, "club": True,
               "key": f"{club['name']}|" + (msg.get("Message-ID") or subject)},
    )


def search(cfg: dict) -> list[Deal]:
    host, user, pw = (env(k) for k in ("IMAP_HOST", "IMAP_USER", "IMAP_PASSWORD"))
    if not (host and user and pw):
        log.info("Newsletter-Mails übersprungen (IMAP_HOST/IMAP_USER/IMAP_PASSWORD fehlen)")
        return []
    mcfg = cfg["sources"]["newsletter_mail"]
    since = (datetime.now() - timedelta(days=int(mcfg.get("lookback_days", 3)))).strftime("%d-%b-%Y")
    deals: list[Deal] = []
    try:
        with imaplib.IMAP4_SSL(host) as imap:
            imap.login(user, pw)
            imap.select("INBOX", readonly=True)
            for club in mcfg.get("clubs", []):
                _, data = imap.search(None, "SINCE", since, "FROM", f'"{club["sender_contains"]}"')
                found = 0
                for num in data[0].split():
                    _, raw = imap.fetch(num, "(BODY.PEEK[])")  # PEEK: Mail bleibt ungelesen
                    msg = email.message_from_bytes(raw[0][1])
                    d = deal_from_message(msg, club, mcfg.get("keywords", []))
                    if d:
                        deals.append(d)
                        found += 1
                log.info("%s: %d passende Aktionen", club["name"], found)
    except (imaplib.IMAP4.error, OSError) as e:
        log.warning("IMAP-Fehler: %s", e)
        ERRORS.append(f"Postfach (IMAP): {e}")
    return deals
