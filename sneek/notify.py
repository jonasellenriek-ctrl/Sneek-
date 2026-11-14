"""Täglicher E-Mail-Report im Sneaker-Look – optional zusätzlich Telegram.

Das HTML ist bewusst tabellenbasiert mit Inline-Styles: so sieht die Mail in
GMX, Gmail, Outlook und Apple Mail gleich aus. Produktbilder werden in die Mail
eingebettet (CID), damit sie auch ohne "Bilder nachladen" erscheinen.
"""
from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape
from typing import Callable
from urllib.parse import urlparse

import requests

from .http import HEADERS, env
from .models import Deal
from .rating import LABELS, rate

log = logging.getLogger(__name__)

SMTP_DEFAULTS = {"imap.gmx.net": "mail.gmx.net", "imap.gmx.com": "mail.gmx.com",
                 "imap.web.de": "smtp.web.de", "imap.gmail.com": "smtp.gmail.com"}

# Farben
INK, PAPER, MUTED, LINE = "#111114", "#ffffff", "#6b6b76", "#ececf0"
ORANGE, PURPLE, GOLD = "#ff5a1f", "#552583", "#fdb927"
FONT = '-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif'

ImageSrc = Callable[[Deal], str]


def _score_color(v: float) -> str:
    return "#16a34a" if v >= 8 else "#f59e0b" if v >= 6 else "#ef4444"


def _host(url: str) -> str:
    return urlparse(url).netloc.removeprefix("www.") or "Shop"


def _money(v: float | None, cur: str) -> str:
    if v is None:
        return ""
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {cur}".strip()


def _bars(r: dict) -> str:
    rows = []
    for k, label in LABELS.items():
        v = r[k]
        pct = int(v * 10)
        rows.append(
            "<tr>"
            f"<td style='font:600 12px {FONT};color:{MUTED};padding:3px 10px 3px 0;width:60px;white-space:nowrap'>{label}</td>"
            "<td style='padding:3px 0'><table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>"
            f"<td width='{pct}%' style='background:{_score_color(v)};height:8px;border-radius:4px;font-size:0;line-height:0'>&nbsp;</td>"
            f"<td width='{100 - pct}%' style='background:{LINE};height:8px;border-radius:4px;font-size:0;line-height:0'>&nbsp;</td>"
            "</tr></table></td>"
            f"<td style='font:700 12px {FONT};color:{INK};padding:3px 0 3px 10px;width:28px;text-align:right'>{v:g}</td>"
            "</tr>"
        )
    return f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0'>{''.join(rows)}</table>"


def _card(d: Deal, is_new: bool, img: str, weights: dict, accent: str) -> str:
    r = rate(d, weights)
    url = escape(d.url, quote=True)
    pct = d.discount_percent or d.extra.get("max_pct")
    pct_txt = (f"-{pct:.0f}%" if d.discount_percent else f"bis -{pct}%") if pct else ""
    size_txt = "US 16 ✓ verfügbar" if d.size_verified else "Größe im Shop prüfen"
    size_col = "#16a34a" if d.size_verified else "#b45309"
    badges = ""
    if is_new:
        badges += (f"<span style='display:inline-block;background:{INK};color:#fff;font:800 10px {FONT};"
                   "letter-spacing:1px;padding:4px 8px;border-radius:999px;margin-right:6px'>NEU</span>")
    if pct_txt:
        badges += (f"<span style='display:inline-block;background:{ORANGE};color:#fff;font:800 11px {FONT};"
                   f"padding:4px 9px;border-radius:999px'>{pct_txt}</span>")

    image_block = ""
    if img:
        image_block = (
            "<tr><td style='background:#f4f4f6;padding:18px;text-align:center;border-radius:12px 12px 0 0'>"
            f"<a href='{url}'><img src='{escape(img, quote=True)}' alt='{escape(d.title, quote=True)}' width='420' "
            "style='display:block;margin:0 auto;width:100%;max-width:420px;height:auto;border:0'></a></td></tr>"
        )

    price_html = ""
    if d.price is not None:
        price_html = f"<span style='font:800 26px {FONT};color:{INK}'>{_money(d.price, d.currency)}</span>"
        if d.old_price:
            price_html += (f"&nbsp;&nbsp;<span style='font:500 15px {FONT};color:{MUTED};text-decoration:line-through'>"
                           f"{_money(d.old_price, d.currency)}</span>")

    note = f"<div style='font:500 12px {FONT};color:{MUTED};margin-top:10px'>{escape(d.note)}</div>" if d.note else ""
    score = r["gesamt"]
    return f"""
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin:0 0 22px;background:{PAPER};border-radius:16px;border-top:5px solid {accent}'>
  {image_block}
  <tr><td style='padding:20px 22px 22px'>
    <table role='presentation' width='100%' cellpadding='0' cellspacing='0'><tr>
      <td style='vertical-align:top'>
        <div style='margin-bottom:8px'>{badges}</div>
        <div style='font:700 11px {FONT};color:{MUTED};text-transform:uppercase;letter-spacing:1.5px'>{escape(_host(d.url))}</div>
        <a href='{url}' style='font:800 19px/1.25 {FONT};color:{INK};text-decoration:none;display:block;margin:4px 0 8px'>{escape(d.title)}</a>
        <div>{price_html}</div>
        <div style='font:600 13px {FONT};color:{size_col};margin-top:6px'>📏 {size_txt}</div>
      </td>
      <td style='vertical-align:top;width:84px;text-align:right'>
        <table role='presentation' cellpadding='0' cellspacing='0' align='right'><tr>
          <td style='width:72px;height:72px;border-radius:36px;background:{_score_color(score)};text-align:center;vertical-align:middle'>
            <div style='font:900 26px/1 {FONT};color:#fff'>{score:g}</div>
            <div style='font:700 9px {FONT};color:#fff;letter-spacing:1px;margin-top:3px'>/ 10</div>
          </td></tr></table>
      </td>
    </tr></table>
    <div style='height:14px;line-height:14px'>&nbsp;</div>
    {_bars(r)}
    {note}
    <table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin-top:16px'><tr>
      <td style='background:{INK};border-radius:12px;text-align:center'>
        <a href='{url}' style='display:block;padding:14px 18px;font:800 15px {FONT};color:#fff;text-decoration:none'>
          Zum Schuh bei {escape(_host(d.url))} &rarr;</a>
      </td></tr></table>
  </td></tr>
</table>"""


def _section(title: str, subtitle: str, color: str, text_color: str = "#fff") -> str:
    return (f"<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='margin:30px 0 16px'><tr>"
            f"<td style='background:{color};border-radius:12px;padding:14px 18px'>"
            f"<div style='font:900 20px {FONT};color:{text_color};letter-spacing:.5px'>{title}</div>"
            f"<div style='font:500 13px {FONT};color:{text_color};opacity:.85;margin-top:2px'>{subtitle}</div>"
            "</td></tr></table>")


def build_report(deals: list[Deal], new: list[Deal], errors: list[str], cfg: dict,
                 image_src: ImageSrc | None = None) -> tuple[str, str]:
    image_src = image_src or (lambda d: d.image)
    weights = cfg.get("rating_weights")
    new_keys = {d.key for d in new}
    focus_cfg = cfg.get("focus") or {}
    focus_name = focus_cfg.get("name", "Fokus")

    def by_score(ds: list[Deal]) -> list[Deal]:
        return sorted(ds, key=lambda d: -rate(d, weights)["gesamt"])

    focus = by_score([d for d in deals if d.extra.get("focus") and not d.extra.get("club")])
    clubs = [d for d in deals if d.extra.get("club")]
    rest = by_score([d for d in deals if not d.extra.get("focus") and not d.extra.get("club")])
    rest = rest[: int(cfg.get("report", {}).get("max_deals", 150))]

    today = datetime.now().strftime("%d.%m.%Y")
    n_new = len(new)
    if focus:
        subject = f"🐍 {len(focus)}× Kobe in US 16 + {len(rest)} Deals – Sneek {today}"
    elif deals:
        subject = f"🏀 {n_new} neue / {len(deals)} Deals in US 16 – Sneek {today}"
    else:
        subject = f"🏀 Heute keine Deals in US 16 – Sneek {today}"

    top = by_score(focus + rest)[:1]
    preheader = (f"Top-Deal: {top[0].title} – {rate(top[0], weights)['gesamt']:g}/10" if top
                 else "Heute nichts Passendes – morgen wieder.")

    stats = "".join(
        f"<td style='background:#c2410c;border-radius:12px;padding:10px 14px'>"
        f"<div style='font:900 22px {FONT};color:#fff'>{v}</div>"
        f"<div style='font:700 10px {FONT};color:#fff;letter-spacing:1px'>{k}</div></td><td style='width:8px'></td>"
        for k, v in (("NEU", n_new), ("KOBE", len(focus)), ("DEALS", len(focus) + len(rest)), ("CLUBS", len(clubs)))
    )
    out = [f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>{escape(subject)}</title></head>
<body style='margin:0;padding:0;background:#0b0b0d'>
<div style='display:none;max-height:0;overflow:hidden;opacity:0'>{escape(preheader)}</div>
<table role='presentation' width='100%' cellpadding='0' cellspacing='0' style='background:#0b0b0d'><tr><td align='center' style='padding:24px 12px'>
<table role='presentation' width='600' cellpadding='0' cellspacing='0' style='width:100%;max-width:600px'>
<tr><td style='background:{ORANGE};border-radius:20px;padding:28px 26px'>
  <div style='font:900 13px {FONT};color:#fff;letter-spacing:4px'>SNEEK · DAILY DROP</div>
  <div style='font:900 34px/1.1 {FONT};color:#fff;margin-top:10px'>Basketballschuhe<br>in US 16 🏀</div>
  <div style='font:600 14px {FONT};color:#fff;margin-top:10px'>{today}</div>
  <table role='presentation' cellpadding='0' cellspacing='0' style='margin-top:18px'><tr>{stats}</tr></table>
</td></tr>
<tr><td>"""]

    out.append(_section(f"🐍 {escape(focus_name)}",
                        f"Nike Kobe in US 16 · ab {focus_cfg.get('min_discount_percent', 0)} % Rabatt", PURPLE, GOLD))
    if focus:
        out += [_card(d, d.key in new_keys, image_src(d), weights, GOLD) for d in focus]
    else:
        out.append(f"<div style='font:500 14px {FONT};color:#a1a1aa;padding:4px 4px 8px'>Heute kein Kobe in US 16 "
                   "mit genug Rabatt gefunden. Der Bot schaut morgen wieder. 🐍</div>")

    if rest:
        out.append(_section("🔥 Top-Deals", f"Basketballschuhe in US 16 · ab {cfg['min_discount_percent']} % Rabatt"
                            " · sortiert nach Bewertung", "#1c1c21"))
        out += [_card(d, d.key in new_keys, image_src(d), weights, ORANGE) for d in rest]

    if clubs:
        out.append(_section("🛍️ Shopping-Clubs", "Zalando Lounge & BestSecret · Aktionen aus deinen Newslettern", "#1f2937"))
        out += [_card(d, d.key in new_keys, image_src(d), weights, "#9ca3af") for d in clubs]

    if not deals:
        out.append(f"<div style='font:500 15px {FONT};color:#d4d4d8;padding:20px 4px'>Heute nichts gefunden, "
                   "das die Kriterien erfüllt. Morgen wieder! 🙂</div>")

    foot = ("Bewertung 1–10 aus Rabatt, Preis, Modell, Größen-Sicherheit und Shop. "
            "„US 16 ✓“ = im Shop als verfügbar bestätigt, sonst bitte selbst prüfen.")
    if errors:
        foot += "<br><br>Nicht erreichbar: " + escape("; ".join(errors))
    out.append(f"<div style='font:500 11px/1.5 {FONT};color:#71717a;padding:24px 6px 8px;text-align:center'>{foot}</div>")
    out.append("</td></tr></table></td></tr></table></body></html>")
    return subject, "".join(out)


def _fetch_images(deals: list[Deal], limit: int = 60) -> dict[str, tuple[str, bytes, str]]:
    """Lädt Produktbilder für die Einbettung: key -> (cid, bytes, subtype)."""
    out: dict[str, tuple[str, bytes, str]] = {}
    for i, d in enumerate([d for d in deals if d.image][:limit]):
        try:
            r = requests.get(d.image, headers=HEADERS, timeout=12)
            ctype = r.headers.get("content-type", "")
            if r.ok and ctype.startswith("image/") and len(r.content) < 1_500_000:
                out[d.key] = (f"img{i}@sneek", r.content, ctype.split("/")[1].split(";")[0])
        except requests.RequestException:
            continue
    return out


def send_report(deals: list[Deal], new: list[Deal], errors: list[str], cfg: dict) -> bool:
    user = env("SMTP_USER") or env("IMAP_USER")
    pw = env("SMTP_PASSWORD") or env("IMAP_PASSWORD")
    host = env("SMTP_HOST") or SMTP_DEFAULTS.get((env("IMAP_HOST") or "").lower())
    to = env("ALERT_EMAIL_TO") or user
    if not (host and user and pw and to):
        log.warning("E-Mail nicht konfiguriert (SMTP_* bzw. IMAP_* Secrets fehlen)")
        return False

    images = _fetch_images(deals)
    subject, html = build_report(
        deals, new, errors, cfg,
        image_src=lambda d: f"cid:{images[d.key][0]}" if d.key in images else d.image,
    )
    msg = MIMEMultipart("related")
    msg["Subject"], msg["From"], msg["To"] = subject, f"Sneek Bot <{user}>", to
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText("\n\n".join(d.format() for d in deals) or "Heute keine Deals.", "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)
    for cid, data, sub in images.values():
        try:
            part = MIMEImage(data, _subtype=sub)
        except (TypeError, ValueError):
            continue
        part.add_header("Content-ID", f"<{cid}>")
        part.add_header("Content-Disposition", "inline", filename=cid.split("@")[0] + "." + sub)
        msg.attach(part)

    try:
        with smtplib.SMTP(host, int(env("SMTP_PORT") or 587), timeout=60) as s:
            s.starttls()
            s.login(user, pw)
            s.send_message(msg)
        log.info("Report an %s gesendet (%d Bilder eingebettet)", to, len(images))
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
