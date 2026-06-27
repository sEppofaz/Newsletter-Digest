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

# Server ziehen + neustarten
ssh root@89.167.104.145 "git -C /opt/newsletter-digest pull && systemctl restart newsletter-digest"
```

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

## Pitfalls
- Bearer-Token nie ins Repo – in `/opt/newsletter-digest/.env`
- Icons-Ordner muss `webhook`-User gehören: `chown webhook:webhook /opt/newsletter-digest/icons`
- nginx proxy_pass mit trailing slash: `/newsletter/` → `http://127.0.0.1:5006/` (Strip des Präfixes)
- In index.html API-Calls mit Prefix: `/newsletter/api/...` (Browser-URL, nicht Flask-intern)
- `cairosvg.svg2png(bytestring=..., ...)` – NICHT `write_to=str(path)` (CAIRO_STATUS_WRITE_ERROR unter gunicorn)
- Gmail App-Passwort erforderlich (kein normales Passwort für IMAP)

## Aktueller Stand
[ ] GitHub-Repo angelegt
[ ] Server: /opt/newsletter-digest/ angelegt
[ ] systemd-Service aktiv
[ ] nginx-Location aktiv
[ ] .env auf Server gesetzt
[ ] Icon-Berechtigungen gesetzt
[ ] n8n Workflow erstellt
[ ] Gmail IMAP aktiviert + App-Passwort generiert
[ ] Erster Test-Digest manuell erstellt (POST /api/process)
[ ] PWA auf Homescreen installiert und getestet
