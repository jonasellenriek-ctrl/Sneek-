"""Benachrichtigungen: Telegram (Push aufs Handy) und/oder E-Mail."""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

import requests

from .models import Deal

log = logging.getLogger(__name__)


def telegram(deals: list[Deal]) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    ok = True
    for d in deals:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": d.format(), "disable_web_page_preview": False},
                timeout=20,
            )
            ok &= r.ok
            if not r.ok:
                log.warning("Telegram-Fehler: %s", r.text[:200])
        except requests.RequestException as e:
            log.warning("Telegram-Fehler: %s", e)
            ok = False
    return ok


def mail(deals: list[Deal]) -> bool:
    host = os.environ.get("SMTP_HOST")
    user, pw = os.environ.get("SMTP_USER"), os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("ALERT_EMAIL_TO") or user
    if not (host and user and pw and to):
        return False
    body = "\n\n" + ("\n\n" + "-" * 40 + "\n\n").join(d.format() for d in deals)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"🏀 Sneek: {len(deals)} neue US-16-Deal(s)"
    msg["From"], msg["To"] = user, to
    try:
        with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", 587)), timeout=30) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError) as e:
        log.warning("Mail-Fehler: %s", e)
        return False


def send(deals: list[Deal]) -> None:
    if not deals:
        return
    for d in deals:
        print("\n" + d.format())
    sent_tg, sent_mail = telegram(deals), mail(deals)
    if not (sent_tg or sent_mail):
        log.warning("Kein Benachrichtigungskanal konfiguriert – Deals nur im Log.")
