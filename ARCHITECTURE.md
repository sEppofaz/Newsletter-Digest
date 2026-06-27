# Newsletter Digest PWA — ARCHITECTURE.md

## Ziel
KI-generierter Newsletter-Digest als PWA auf dem Hetzner VPS.
Kategorien: KI & Tech, Finanzen, Automobil, Lokal (Bayerbach, Hölskofen, Oberköllnbach, Paindlkofen).
Frequenz: einstellbar (täglich / wöchentlich / monatlich).

---

## Stack

| Komponente | Technologie | Hinweis |
|---|---|---|
| Mail-Eingang | Gmail (josef.jf.fischer@gmail.com) | IMAP + App-Passwort |
| Workflow-Engine | n8n (bereits auf VPS) | Cron täglich 07:00 |
| KI-Summarization | Claude API — `claude-haiku-4-5-20251001` | Bulk/Kategorie, kostengünstig |
| Backend | Flask (Python 3.11) + gunicorn | Port 5006 |
| Frontend | PWA (Vanilla JS + Manifest + Service Worker) | standalone, alle in index.html |
| Hosting | Hetzner VPS (CX23, Ubuntu 24.04) | bestehender Server |
| Push | Telegram Bot | **nur Fehler-Alerts**, kein Digest-Inhalt |

---

## Datenfluss

```
Gmail (IMAP)
    │
    ▼
n8n Cron Node (täglich 07:00)
    │
    ├─ GET /api/should_run → false? → Stopp (kein Ausgabe-Tag)
    │                      → true?  → weiter
    │
    ├─ IMAP Node: ungelesene Mails abrufen (seit 24h)
    │
    ├─ Function Node: Absender → Kategorie
    │   (liest Mapping aus GET /api/config → senders)
    │
    ▼
POST /api/process (Bearer-Token)
    Body: { date, mails: [{from, subject, body, category}] }
    │
    ▼
Flask /api/process
    │
    ├─ Mails nach Kategorie gruppieren
    ├─ Pro Kategorie: Claude Haiku API
    │   └─ Bei Modell-Fehler: Auto-Fallback + Telegram-Alert
    ├─ Digest zusammenstellen
    ├─ digest_YYYY-MM-DD.json speichern
    └─ Alte Digests bereinigen (max_archive)
    │
    ▼
PWA liest GET /api/digest/latest → rendert Digest
```

---

## Verzeichnisstruktur (Server)

```
/opt/newsletter-digest/
├── app.py                  # Flask-App (API + Icon-Generierung)
├── config.json             # Laufende Konfiguration (Zeitplan, Senders, ...)
├── requirements.txt
├── .env                    # Secrets (nie ins Repo!)
├── venv/
├── data/
│   └── digests/            # digest_YYYY-MM-DD.json
├── icons/                  # cairosvg-generierte Icons (chown webhook!)
├── index.html              # PWA Shell
├── manifest.json
├── sw.js
└── CLAUDE.md
```

---

## Flask API Endpunkte

| Methode | Pfad | Auth | Beschreibung |
|---|---|---|---|
| POST | /api/process | Bearer | n8n liefert Mails → Flask ruft Claude auf → speichert Digest |
| GET | /api/digest/latest | – | PWA lädt aktuellen Digest |
| GET | /api/digest/\<date\> | – | Archiv-Abruf (YYYY-MM-DD) |
| GET | /api/digest/list | – | Liste aller verfügbaren Datum-Strings |
| GET | /api/should_run | – | n8n prüft ob heute Ausgabe-Tag ist |
| GET | /api/config | – | Aktuelle Config (inkl. Senders) |
| POST | /api/config | Bearer | Config aktualisieren (PWA Settings) |
| GET | /api/status | – | Health Check |

---

## Config-Schema (config.json)

```json
{
  "schedule": {
    "type": "weekly",          // "daily" | "weekly" | "monthly"
    "weekday": "sunday",       // weekly: Wochentag; monthly: Wochentag des n-ten
    "week": 1                  // nur monthly: 1=erster, 2=zweiter, ...
  },
  "max_archive": 10,           // ältere Digests werden gelöscht
  "bullet_points": 10,         // Anzahl Punkte pro Kategorie im System-Prompt
  "senders": {
    "dan@tldrnewsletter.com": "ki_tech"
  }
}
```

---

## Claude Haiku – Prompt-Design

### System Prompt (pro Kategorie)
```
Du bist ein redaktioneller Assistent für den Bereich: {cat_context}.
Genau {bullet_points} Punkte.
Jeder Punkt: **Kurze prägnante Überschrift** – 2–3 Sätze Erläuterung, sachlich und informativ.
Wichtigstes zuerst, kein Marketing-Sprech.
Letzter Absatz (eigene Zeile): _Relevanz heute: [1 Satz]_
Antwort ausschließlich auf Deutsch.
```

### Modell-ID Absicherung
- Konfiguriert: `CLAUDE_MODEL` (aus .env, default: `claude-haiku-4-5-20251001`)
- Bei `400/404 model_not_found`: automatischer Retry mit Fallback-ID + Telegram-Alert
- **Wichtig:** Modell-ID muss immer mit Datum-Suffix sein (`...-20251001`)

### Kostenschätzung (10 Bullet Points, 4 Kategorien)
- ~15 Mails/Tag à ~2.000 Token Input = ~30.000 Token Input
- Output ~3.000 Token/Kategorie × 4 = ~12.000 Token Output/Ausgabe
- Bei wöchentlicher Ausgabe: ~$0,05/Monat

---

## n8n Workflow – Nodes (Reihenfolge)

1. **Cron** — täglich 07:00
2. **HTTP Request** — GET /api/should_run → `run: false` → Workflow-Stop
3. **IMAP** — Gmail abrufen, nur ungelesen, seit 24h
4. **HTTP Request** — GET /api/config → `senders`-Dict laden
5. **Function** — Absender-Email gegen `senders`-Dict → `category` zuweisen
6. **HTTP Request** — POST /api/process (alle Mails, Bearer-Token)
   Body: `{ "date": "{{$now.format('YYYY-MM-DD')}}", "mails": [...] }`

---

## Kategorien

| ID | Name | Kontext für Claude |
|---|---|---|
| `ki_tech` | KI & Tech | KI, Machine Learning, Software-Entwicklung und Technologie |
| `finanzen` | Finanzen | Finanzmärkte, Wirtschaft, Aktien und Unternehmen |
| `automobil` | Automobil | Automobil, E-Mobilität, Motorrad und Verkehr |
| `lokal` | Lokal | Lokale Nachrichten aus Bayerbach, Hölskofen, Oberköllnbach und Paindlkofen (Niederbayern, LK Dingolfing-Landau) |

---

## PWA Frontend – Features

- Offline-fähig (Service Worker cacht letzten Digest)
- Dark/Light Mode (CSS custom properties)
- Kategorien als Tabs
- Archiv-Dropdown (letzte `max_archive` Ausgaben)
- Settings-Overlay: Zeitplan, Archiv-Tiefe, Bullet Points, Absender-Mapping
- Pull-to-Refresh, Scroll-to-Top, Info-Sheet
- Admin-Token im `localStorage` gespeichert (für Settings-Schreibzugriff)
- Kein Login erforderlich (internes Tool)

---

## nginx-Location

```nginx
location /newsletter/ {
    proxy_pass http://127.0.0.1:5006/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    add_header Cache-Control "no-store";
}
```

---

## systemd-Service

```ini
[Unit]
Description=Newsletter Digest
After=network.target

[Service]
User=webhook
WorkingDirectory=/opt/newsletter-digest
ExecStart=/opt/newsletter-digest/venv/bin/gunicorn -w 2 -b 127.0.0.1:5006 app:app
Restart=always
EnvironmentFile=/opt/newsletter-digest/.env

[Install]
WantedBy=multi-user.target
```

---

## Offene Punkte

- [ ] Gmail IMAP aktivieren + App-Passwort generieren
- [ ] .env auf Server befüllen (ANTHROPIC_API_KEY, BEARER_TOKEN, Telegram)
- [ ] n8n Workflow erstellen
- [ ] Absender-Adressen nach ersten eingehenden Mails verifizieren und in Config nachtragen
- [ ] Archiv-Tiefe für Digest-Bereinigung per Cron prüfen (automatisch bei POST /api/process)
