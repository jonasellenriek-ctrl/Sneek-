# 🏀 Sneek – Deal-Bot für Basketballschuhe in US 16

Sneek sucht alle 30 Minuten automatisch nach **stark reduzierten Basketballschuhen in Größe US 16**
(EU 50.5 / UK 15) und schickt dir neue Treffer aufs Handy (Telegram) und/oder per E-Mail.
Bereits gemeldete Deals kommen nicht doppelt. Fällt der Preis weiter, wirst du erneut benachrichtigt.

## Woher die Deals kommen

| Quelle | Was sie abdeckt | Größe 16 geprüft? |
|---|---|---|
| **Shopify-Shops** (Shoe Palace, Jimmy Jazz, DTLR, Kith, Overkill, …) | direkt aus dem Shop-Katalog, inkl. Lagerbestand | ✅ ja, nur verfügbare US-16-Paare |
| **Google Shopping** (über SerpAPI) | so gut wie alle Shops: Zalando, About You, Snipes, Foot Locker, Nike, adidas, Kickz, Amazon, eBay … | ⚠️ Preis/Rabatt ja, Größe bitte im Shop prüfen |
| **Zalando Lounge** (über deine Newsletter-Mails) | jede neue Lounge-Aktion mit Nike, Jordan, adidas, Basketball usw. | ⚠️ Größe in der Aktion prüfen |

> **Warum Zalando Lounge über E-Mail?** Die Lounge ist nur eingeloggt sichtbar, und die AGB verbieten
> automatisiertes Auslesen. Jede Aktion wird aber per Mail angekündigt. Der Bot liest diese Mails
> **nur lesend** aus deinem Postfach und meldet die relevanten Aktionen.

## Einrichtung (ca. 10 Minuten)

Alle Zugangsdaten kommen als **Secrets** in GitHub:
*Repo → Settings → Secrets and variables → Actions → New repository secret*.

### 1. Telegram-Benachrichtigung (empfohlen)
1. In Telegram **@BotFather** öffnen → `/newbot` → Token kopieren → Secret `TELEGRAM_BOT_TOKEN`.
2. Deinem neuen Bot eine beliebige Nachricht schreiben.
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` im Browser öffnen → `"chat":{"id": ...}` → Secret `TELEGRAM_CHAT_ID`.

### 2. Google Shopping = „das ganze Internet“
1. Kostenloses Konto auf [serpapi.com](https://serpapi.com) anlegen → API-Key → Secret `SERPAPI_KEY`.
2. Standard: 4 Suchen alle 12 h ≈ 240 Suchen/Monat. Liegt das über deinem Gratis-Kontingent,
   in `config.yaml` `min_interval_hours` erhöhen oder Suchbegriffe streichen.

### 3. Zalando Lounge (über dein Postfach)
Zalando-Lounge-Newsletter aktivieren und z. B. bei GMX:
- In GMX unter *Einstellungen → POP3/IMAP* den IMAP-Zugriff erlauben.
- Secrets: `IMAP_HOST` = `imap.gmx.net`, `IMAP_USER` = deine Mail-Adresse, `IMAP_PASSWORD` = dein Passwort
  (oder ein App-Passwort, falls aktiviert).

### 4. Optional: Benachrichtigung per E-Mail
`SMTP_HOST` (`mail.gmx.net`), `SMTP_PORT` (`587`), `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_TO`.

### 5. Starten
*Actions → „Sneek Deal-Suche“ → Run workflow.* Danach läuft der Bot automatisch alle 30 Minuten.
Hinweis: GitHub startet geplante Workflows nur auf dem **Standard-Branch** (`main`) und kann sie
bei hoher Last ein paar Minuten verzögern.

## Anpassen – `config.yaml`
- `min_discount_percent`: ab wie viel Rabatt gemeldet wird (Standard **40 %**)
- `max_price`: Preisobergrenze
- `size_aliases`: wie US 16 in den Shops heißt (Nike EU 50.5, adidas EU 51 1/3 …)
- `basketball_keywords` / `exclude_keywords`: was als Basketballschuh zählt
- `sources.shopify.shops`: weitere Shopify-Shops eintragen (Test: `https://shop.de/products.json` im Browser liefert JSON)
- `sources.google_shopping.queries`: eigene Suchbegriffe

## Lokal ausführen
```bash
pip install -r requirements.txt
python -m sneek.main --dry-run   # zeigt Treffer, sendet nichts
python -m pytest                 # Tests
```
