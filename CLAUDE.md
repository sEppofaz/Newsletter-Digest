# Newsletter Digest – Claude Code Kontext

## Projekt
Täglicher KI-generierter Newsletter-Digest als Flask/PWA auf Hetzner VPS.
Kategorien: KI & Tech, Finanzen, Automobil, Lokal (Bayerbach/Hölskofen/Oberköllnbach/Paindlkofen)

## Live-URL
`https://umbenennen.duckdns.org/newsletter/`

## Architektur
Siehe `ARCHITECTURE.md` (im selben Ordner)

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
- n8n für Workflow-Orchestrierung (bereits auf Server vorhanden)
- Gmail IMAP: `josef.jf.fischer@gmail.com`

## n8n Workflow
- Cron täglich 07:00
- GET /api/should_run → falls false: stopp
- IMAP: ungelesene Mails seit 24h
- Function Node: Absender → Kategorie (per GET /api/config)
- POST /api/process (Bearer-Token) → Flask ruft Claude auf → Digest gespeichert

## Wichtige Architektur-Entscheidung
n8n ruft Claude NICHT direkt auf. Alle Mails gehen per POST /api/process an Flask.
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

## Pitfalls
- Bearer-Token nie ins Repo – in `/opt/newsletter-digest/.env`
- Icons-Ordner muss `webhook`-User gehören: `chown webhook:webhook /opt/newsletter-digest/icons`
- nginx proxy_pass mit trailing slash: `/newsletter/` → `http://127.0.0.1:5006/` (Strip des Präfixes)
- In index.html API-Calls mit Prefix: `/newsletter/api/...` (Browser-URL, nicht Flask-intern)
- `cairosvg.svg2png(bytestring=..., ...)` – NICHT `write_to=str(path)` (CAIRO_STATUS_WRITE_ERROR unter gunicorn)
- Gmail App-Passwort erforderlich (kein normales Passwort für IMAP)
- config.json auf Server kann durch PWA geändert werden – bei git pull Konflikt: `git stash && git pull && git stash drop`
- `call_claude()` erwartet `cat_cfg`-Dict (nicht category-String + bullet_points-Int)
- Nach git pull als root: `chown webhook:webhook /opt/newsletter-digest/config.json` – sonst 500 beim Einstellungen speichern (PermissionError)

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
