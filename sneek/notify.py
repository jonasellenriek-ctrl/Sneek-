"""Täglicher E-Mail-Report (HTML) – optional zusätzlich Telegram."""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape

import requests

from .http import env
from .models import Deal

log = logging.getLogger(__name__)

SMTP_DEFAULTS = {"imap.gmx.net": "mail.gmx.net", "imap.gmx.com": "mail.gmx.com",
                 "imap.web.de": "smtp.web.de", "imap.gmail.com": "smtp.gmail.com"}


def _row(d: Deal, new: bool) -> str:
    price = ""
    if d.price is not None:
        price = f"<b>{d.price:.2f} {escape(d.currency)}</b>"
        if d.old_price:
            price += f"<br><s style='color:#888'>{d.old_price:.2f}</s>"
    pct = f"-{d.discount_percent:.0f}%" if d.discount_percent else (
        f"bis -{d.extra['max_pct']}%" if d.extra.get("max_pct") else "")
    size = escape(d.size) + (" ✅" if d.size_verified else "") if d.size else "prüfen ⚠️"
    badge = "<span style='background:#e8590c;color:#fff;border-radius:4px;padding:1px 6px;font-size:11px'>NEU</span> " if new else ""
    return (
        "<tr style='border-bottom:1px solid #eee'>"
        f"<td style='padding:8px'>{badge}<a href='{escape(d.url, quote=True)}' style='color:#1a5fb4;text-decoration:none'><b>{escape(d.title)}</b></a>"
        f"<br><span style='color:#666;font-size:12px'>{escape(d.source)}{' · ' + escape(d.note) if d.note else ''}</span></td>"
        f"<td style='padding:8px;text-align:right;white-space:nowrap'>{price}</td>"
        f"<td style='padding:8px;text-align:right;color:#c92a2a;font-weight:bold;white-space:nowrap'>{pct}</td>"
        f"<td style='padding:8px;white-space:nowrap'>{size}</td></tr>"
    )


def _table(deals: list[Deal], new_keys: set[str]) -> str:
    head = ("<tr style='background:#f4f4f4;text-align:left'><th style='padding:8px'>Schuh</th>"
            "<th style='padding:8px;text-align:right'>Preis</th><th style='padding:8px;text-align:right'>Rabatt</th>"
            "<th style='padding:8px'>Größe</th></tr>")
    rows = "".join(_row(d, d.key in new_keys) for d in deals)
    return f"<table style='border-collapse:collapse;width:100%;font-size:14px'>{head}{rows}</table>"


def build_report(deals: list[Deal], new: list[Deal], errors: list[str], cfg: dict) -> tuple[str, str]:
    new_keys = {d.key for d in new}
    clubs = [d for d in deals if d.extra.get("club")]
    shoes = [d for d in deals if not d.extra.get("club")][: int(cfg.get("report", {}).get("max_deals", 150))]
    today = datetime.now().strftime("%d.%m.%Y")
    subject = f"🏀 Sneek {today}: {len(new)} neue / {len(deals)} Deals in US 16"
    if not deals:
        subject = f"🏀 Sneek {today}: heute keine Deals in US 16"

    parts = [
        "<div style='font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:760px;margin:auto;color:#222'>",
        f"<h2 style='margin-bottom:4px'>🏀 Basketballschuhe US 16 – {today}</h2>",
        f"<p style='color:#555;margin-top:0'>Ab {cfg['min_discount_percent']}% Rabatt · "
        f"<b>{len(new)}</b> neu seit gestern · {len(deals)} insgesamt</p>",
    ]
    if shoes:
        parts += ["<h3>Schuhe</h3>", _table(shoes, new_keys)]
    if clubs:
        parts += ["<h3>Shopping-Club-Aktionen (Zalando Lounge / BestSecret)</h3>",
                  "<p style='color:#555;font-size:13px'>Aus deinen Newslettern – Größe in der Aktion prüfen.</p>",
                  _table(clubs, new_keys)]
    if not deals:
        parts.append("<p>Heute nichts gefunden, das die Kriterien erfüllt. Morgen wieder! 🙂</p>")
    if errors:
        parts.append("<p style='color:#888;font-size:12px;margin-top:24px'>Nicht erreichbar in diesem Lauf: "
                     + escape("; ".join(errors)) + "</p>")
    parts.append("<p style='color:#aaa;font-size:11px'>Größe ✅ = im Shop als verfügbar bestätigt · "
                 "⚠️ = bitte selbst prüfen. Einstellungen: config.yaml</p></div>")
    return subject, "".join(parts)


def send_email(subject: str, html: str) -> bool:
    user = env("SMTP_USER") or env("IMAP_USER")
    pw = env("SMTP_PASSWORD") or env("IMAP_PASSWORD")
    host = env("SMTP_HOST") or SMTP_DEFAULTS.get((env("IMAP_HOST") or "").lower())
    to = env("ALERT_EMAIL_TO") or user
    if not (host and user and pw and to):
        log.warning("E-Mail nicht konfiguriert (SMTP_* bzw. IMAP_* Secrets fehlen)")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    msg.attach(MIMEText("Bitte HTML-Ansicht verwenden.", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP(host, int(env("SMTP_PORT") or 587), timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        log.info("Report an %s gesendet", to)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.error("Mail-Fehler: %s", e)
        return False


def telegram(deals: list[Deal]) -> None:
    """Optional: neue Deals zusätzlich sofort per Telegram."""
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    for d in deals:
        try:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": d.format()}, timeout=20)
        except requests.RequestException as e:
            log.warning("Telegram-Fehler: %s", e)
