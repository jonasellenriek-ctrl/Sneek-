# 🏀 Sneek – Deal-Bot für Basketballschuhe in US 16

Sneek sucht **jeden Morgen automatisch** nach **stark reduzierten Basketballschuhen in Größe US 16**
(EU 50.5 / UK 15) und schickt dir einen **Tages-Report per E-Mail**: alle aktuellen Deals,
sortiert nach Rabatt, neue seit gestern mit „NEU“ markiert. Dazu die passenden Aktionen von
**Zalando Lounge** und **BestSecret**.

## Woher die Deals kommen

| Quelle | Was sie abdeckt | Größe 16 geprüft? |
|---|---|---|
| **Shopify-Shops** (Shoe Palace, Jimmy Jazz, DTLR, Kith, Overkill, …) | direkt aus dem Shop-Katalog, inkl. Lagerbestand | ✅ ja, nur verfügbare US-16-Paare |
| **Google Shopping** (über SerpAPI) | so gut wie alle Shops: Zalando, About You, Snipes, Foot Locker, Nike, adidas, Kickz, Amazon, eBay … | ⚠️ Preis/Rabatt ja, Größe bitte im Shop prüfen |
| **Zalando Lounge & BestSecret** (über deine Newsletter-Mails) | jede neue Aktion mit Nike, Jordan, adidas, Basketball usw. | ⚠️ Größe in der Aktion prüfen |

> **Warum Zalando Lounge / BestSecret über E-Mail?** Beide sind nur eingeloggt sichtbar, und ihre AGB
> verbieten automatisiertes Auslesen. Ein Login-Bot riskiert eine Kontosperre. Jede Aktion wird aber
> per Newsletter angekündigt. Der Bot liest diese Mails **nur lesend** aus deinem Postfach
> (sie bleiben ungelesen) und übernimmt die relevanten Aktionen in den Report.

## Einrichtung (ca. 10 Minuten)

Alle Zugangsdaten kommen als **Secrets** in GitHub:
*Repo → Settings → Secrets and variables → Actions → New repository secret*.

### 1. Postfach (Pflicht – für Report-Versand und Newsletter)
Beispiel GMX:
1. In GMX unter *E-Mail → Einstellungen → POP3/IMAP Abruf* den Haken bei
   „POP3 und IMAP Zugriff erlauben“ setzen (damit gehen auch IMAP und SMTP).
2. Secrets anlegen:
   - `IMAP_HOST` = `imap.gmx.net`
   - `IMAP_USER` = deine GMX-Adresse
   - `IMAP_PASSWORD` = dein GMX-Passwort (bzw. App-Passwort, falls 2FA aktiv)

Der Report wird über denselben Account verschickt (bei GMX automatisch über `mail.gmx.net`)
und landet in genau diesem Postfach. Andere Empfänger-Adresse: Secret `ALERT_EMAIL_TO`.
Anderer Anbieter: zusätzlich `SMTP_HOST` (und ggf. `SMTP_PORT`, Standard 587) setzen.

3. Im **Zalando-Lounge-** und im **BestSecret-Konto** den Newsletter aktivieren, an diese Adresse.

### 2. Google Shopping = „das ganze Internet“ (empfohlen)
1. Kostenloses Konto auf [serpapi.com](https://serpapi.com) anlegen → API-Key → Secret `SERPAPI_KEY`.
2. Standard: 4 Suchen pro Tag ≈ 120 Suchen/Monat.

### 3. Starten
1. Diesen Stand auf den Standard-Branch (`main`) bringen – GitHub führt geplante Läufe nur dort aus.
2. *Actions → „Sneek Tages-Report“ → Run workflow* – nach ein paar Minuten ist der erste Report da.
3. Danach kommt er automatisch **jeden Morgen gegen 7–8 Uhr**.

### Optional: zusätzlich Telegram-Push bei neuen Deals
In Telegram **@BotFather** → `/newbot` → Token als `TELEGRAM_BOT_TOKEN`; dem Bot schreiben, dann
`https://api.telegram.org/bot<TOKEN>/getUpdates` öffnen → `chat.id` als `TELEGRAM_CHAT_ID`.

## Anpassen – `config.yaml`
- `report.send_empty`: auch an Tagen ohne Deals eine kurze Mail schicken (Standard: ja)
- Uhrzeit: in `.github/workflows/sneek.yml` die `cron`-Zeile (UTC)
- `min_discount_percent`: ab wie viel Rabatt gemeldet wird (Standard **40 %**)
- `max_price`: Preisobergrenze
- `size_aliases`: wie US 16 in den Shops heißt (Nike EU 50.5, adidas EU 51 1/3 …)
- `basketball_keywords` / `exclude_keywords`: was als Basketballschuh zählt
- `sources.shopify.shops`: weitere Shopify-Shops eintragen (Test: `https://shop.de/products.json` im Browser liefert JSON)
- `sources.google_shopping.queries`: eigene Suchbegriffe

## Lokal ausführen
```bash
pip install -r requirements.txt
python -m sneek.main --dry-run --preview report.html   # nichts senden, Report als Datei
python -m pytest                 # Tests
```
