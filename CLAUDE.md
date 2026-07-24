# Newsletter Digest – Claude Code Kontext

## Projekt
Täglicher KI-generierter Newsletter-Digest als Flask/PWA auf Hetzner VPS.
Kategorien: KI & Tech, Finanzen, Automobil, Lokal (Bayerbach/Hölskofen/Oberköllnbach/Paindlkofen)

## Live-URL
`https://umbenennen.duckdns.org/newsletter/`

## Architektur
`ARCHITECTURE.md` (im selben Ordner) ist die ursprüngliche Planung – **veraltet**, sah n8n als Workflow-Engine vor. Tatsächlich umgesetzt: systemd-Timer statt n8n (siehe ADR-001). Aktueller Ablauf: Abschnitt „Fetch-Workflow" unten.

## Deployment
```bash
# Lokal committen + pushen
git -C ~/Dropbox/Apps/Claude/Newsletter add <datei>
git -C ~/Dropbox/Apps/Claude/Newsletter commit -m "..."
git -C ~/Dropbox/Apps/Claude/Newsletter push

# Server ziehen + Rechte reparieren + neustarten
ssh root@89.167.104.145 "git -C /opt/newsletter-digest pull && chown webhook:webhook /opt/newsletter-digest/config.json && systemctl restart newsletter-digest"
```

⚠️ **Nach jedem git pull:** `config.json` gehört danach root (git pull als root) → gunicorn (User: webhook) kann nicht schreiben → Einstellungen speichern schlägt mit 500 fehl. Immer `chown webhook:webhook /opt/newsletter-digest/config.json` nach dem Pull ausführen.

## Server-Pfade
- App: `/opt/newsletter-digest/`
- venv: `/opt/newsletter-digest/venv/`
- Daten: `/opt/newsletter-digest/data/digests/`
- Icons: `/opt/newsletter-digest/icons/`
- Config: `/opt/newsletter-digest/config.json`
- Env: `/opt/newsletter-digest/.env` (nie ins Repo!)
- Logs: `journalctl -u newsletter-digest -f`

## Service
- systemd: `newsletter-digest.service`
- Port: 5006
- User: `webhook`

## nginx
- vhost: `umbenennen.duckdns.org`
- Location: `/newsletter/` → Port 5006

## Stack
- Python 3.11, Flask, gunicorn
- cairosvg für Icon-Generierung
- Claude Haiku API (Modell: `claude-haiku-4-5-20251001`, Fallback hardcoded)
- systemd-Timer für Workflow-Orchestrierung (kein n8n – siehe ADR-001, n8n war nie auf dem Server installiert)
- Gmail IMAP: `josef.jf.fischer@gmail.com`

## Fetch-Workflow (fetch_mails.py + newsletter-fetch.timer)
- `newsletter-fetch.timer` stündlich → `newsletter-fetch.service` (OneShot) startet `fetch_mails.py`
- GET /api/should_run → falls false: sofortiger Abbruch
- IMAP: ungelesene Mails seit 24h
- Absender → Kategorie: Mapping aus config.json, sonst Claude-Haiku-Auto-Kategorisierung (ADR-002)
- POST /api/process (Bearer-Token) → Flask ruft Claude auf → Digest gespeichert (ADR-001, ADR-003)

## Wichtige Architektur-Entscheidung
`fetch_mails.py` ruft Claude NICHT direkt für die Zusammenfassung auf. Alle Mails gehen per POST /api/process an Flask.
Flask macht den Claude-API-Call (zentrale Haiku-Modell-Validierung + Fallback).
Bei ungültiger Modell-ID: automatischer Fallback + Telegram-Alert.

## SW-Cache-Name
`newsletter-v1` – bei Icon/Manifest-Änderungen hochzählen → `newsletter-v2`

## Icon
Lucide newspaper-ähnlich, Hintergrundfarbe `#1e3a5f` (Dunkelblau)
Methode B (cairosvg, server-seitig), generiert in `/opt/newsletter-digest/icons/`

## Config-Schema (config.json)
```json
{
  "schedule": {"type": "weekly|daily|monthly", "weekday": "sunday", "week": 1, "hour": 7},
  "max_archive": 10,
  "categories": [
    {"id": "ki_tech", "name": "KI & Tech", "enabled": true, "bullet_points": 10,
     "keywords": ["Claude", "OpenAI"], "context": "KI, Technologie…"}
  ],
  "senders": {"dan@tldrnewsletter.com": "ki_tech"}
}
```
- `categories[].keywords` → in Claude-Prompt priorisiert: „Besonders relevant: X, Y"
- `categories[].enabled: false` → Rubrik komplett überspringen
- Timer läuft **stündlich**, fetch_mails.py prüft `should_run_today()` → vergleicht `now.hour == schedule.hour`

## Nachhol-Digest (manuell, bei ausgefallenem Digest)
```bash
ssh root@89.167.104.145
cd /opt/newsletter-digest
venv/bin/python3 fetch_mails.py --catchup-days 14
```
Durchsucht `[Gmail]/All Mail` (nicht INBOX, da ältere Mails ggf. schon archiviert sind) rein lesend, N Tage zurück, umgeht `should_run()`. Schreibt normal `digest_<heute>.json` über denselben `process_mails()`-Pfad inkl. Kosten-Hard-Kill-Schutz. Vor Nutzung sicherstellen, dass Kosten-Tracking aktiv ist (siehe unten) – bei vielen Tagen potenziell teurer als ein normaler Lauf.

## Kosten-Tracking (seit 2026-07-24)
`costs.py` trackt jeden Claude-Call (Kategorie-Zusammenfassung in `app.py` + Auto-Kategorisierung in `fetch_mails.py`) in `claude_costs.json` (gitignored, USD, pro Call + Tag/Woche/Monat/Jahr). Session = ein Kalendertag.
- **1$/Tag:** Telegram-Info, Verarbeitung läuft normal weiter.
- **5$/Tag:** Selbstständiger Abbruch der restlichen Verarbeitung (verbleibende Kategorien/unbekannte Absender werden übersprungen, bereits Fertiges bleibt gespeichert). Kein Warten auf Bestätigung.
- Sichtbar über `/api/costs` + Kosten-Overlay in der PWA (Header-Button neben Einstellungen).
- Details: ADR-004, `PKA/BKM/Claude-API-Kosten-Tracking.md`.

## Pitfalls
- **Gunicorn-Timeout:** `newsletter-digest.service` läuft mit `--timeout 120` (seit 2026-07-24, davor kein Flag = Gunicorn-Default 30s). Claude-Call in `call_claude()` erlaubt `timeout=90` – bei Gunicorn-Timeout < Requests-Timeout killt Gunicorn den Worker mitten in der Anfrage (`WORKER TIMEOUT`/`SIGABRT`) → 500 bei `/api/process`, fetch_mails.py meldet die leere Digest-Seite mit Warning. Bei künftigen Änderungen am `timeout=90` in `app.py` den Gunicorn-Wert in der `.service`-Datei entsprechend nachziehen (Gunicorn-Wert immer > Requests-Timeout)
- `telegram_alert()`/`notify_telegram()` splitten Nachrichten >4096 Zeichen automatisch (siehe `PKA/BKM/Telegram-Integration.md`)
- Bearer-Token nie ins Repo – in `/opt/newsletter-digest/.env`
- Icons-Ordner muss `webhook`-User gehören: `chown webhook:webhook /opt/newsletter-digest/icons`
- nginx proxy_pass mit trailing slash: `/newsletter/` → `http://127.0.0.1:5006/` (Strip des Präfixes)
- In index.html API-Calls mit Prefix: `/newsletter/api/...` (Browser-URL, nicht Flask-intern)
- `cairosvg.svg2png(bytestring=..., ...)` – NICHT `write_to=str(path)` (CAIRO_STATUS_WRITE_ERROR unter gunicorn)
- Gmail App-Passwort erforderlich (kein normales Passwort für IMAP)
- config.json auf Server kann durch PWA geändert werden – bei git pull Konflikt: `git stash && git pull && git stash drop`
- `call_claude()` erwartet `cat_cfg`-Dict (nicht category-String + bullet_points-Int)
- Nach git pull als root: `chown webhook:webhook /opt/newsletter-digest/config.json` – sonst 500 beim Einstellungen speichern (PermissionError)
- Nach dem Digest-Lauf werden erfolgreich kategorisierte Mails automatisch als gelesen markiert und in `[Gmail]/All Mail` archiviert (aus INBOX entfernt). Unkategorisierte Mails bleiben im INBOX
- `costs.py`/`_load()`: bei bereits existierender `claude_costs.json` im Alt-Format immer `dict.update(raw)` auf einen Default-Dict, nie `return raw` direkt – sonst `KeyError` auf neue Keys (`calls`/`daily`), live gefunden beim Sentiment-Scanner-Rollout (2026-07-24)
- **Server-Drift-Warnung:** Diese Archivierungsfunktion in `fetch_mails.py` wurde am 2026-06-29 direkt auf dem Server implementiert und erst am 2026-07-24 (bei einem `git pull`-Konflikt) ins Repo zurückgeholt – bis dahin unsynchronisiert. Vor jedem Deploy prüfen (`ssh ... "cd /opt/newsletter-digest && git status"`), ob der Server unerwartete lokale Änderungen an `.py`-Dateien hat (nicht nur `config.json`, das ist normal) – sonst droht stillschweigender Feature-Verlust beim Überschreiben

## Aktueller Stand
[x] GitHub-Repo angelegt (sEppofaz/Newsletter-Digest)
[x] Server: /opt/newsletter-digest/ angelegt
[x] systemd-Service aktiv (newsletter-digest.service, Port 5006)
[x] systemd-Timer aktiv (newsletter-fetch.timer, stündlich)
[x] nginx-Location aktiv (/newsletter/)
[x] .env auf Server gesetzt (ANTHROPIC_API_KEY, CLAUDE_MODEL, BEARER_TOKEN, TELEGRAM_*, GMAIL_*)
[x] Icon-Berechtigungen gesetzt (chown webhook)
[x] Gmail IMAP aktiviert + App-Passwort generiert (josef.jf.fischer@gmail.com)
[x] Erster Test-Digest manuell erstellt und in PWA gerendert
[x] Auto-Kategorisierung per Claude Haiku (kein manuelles Mapping nötig)
[x] Volle Rubrik-Variabilität: An/Aus, Name, Context, Bullets, Keywords, neue Rubriken
[x] Uhrzeit-Picker in PWA-Einstellungen
[x] Dynamische Tabs aus Config
[x] Double-Opt-In-Mails bestätigt (11 Newsletter)
[x] PWA auf Homescreen installiert
