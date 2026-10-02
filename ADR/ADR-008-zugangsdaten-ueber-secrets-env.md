# ADR-008: Zugangsdaten über `/etc/pka/secrets.env` (Präfix `NL_`) statt eigener `.env`

**Datum:** 2026-10-02
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem
Der Newsletter-Dienst hielt seine Zugangsdaten (Anthropic-, OpenAI-, Telegram-, Gmail-, Dropbox-Zugang, Bearer-Token) in einer eigenen `/opt/newsletter-digest/.env`. Josefs Regel: Passwörter und Token stehen **nur** in `/etc/pka/secrets.env`. Ein Server-Scan am 2026-10-02 fand die `.env` als Verstoß.

## Entscheidung
- Die Werte stehen in `secrets.env` mit Präfix **`NL_`** (`NL_ANTHROPIC_API_KEY`, `NL_TELEGRAM_BOT_TOKEN`, …).
- `envquelle.py` (`EnvQuelle`) liest je Name zuerst `NL_<NAME>` aus der Umgebung, dann (Übergang) die `.env`. Variablen **ohne** Präfix werden ignoriert.
- Beide Units (`newsletter-digest`, `newsletter-fetch`) laden `EnvironmentFile=/etc/pka/secrets.env` über ein Drop-in `10-secrets.conf` (leeres `EnvironmentFile=` setzt die alte Zeile zurück).
- Der Umzug lief über ein Skript, das Josef selbst ausführte (`/root/nl_umzug.sh`): es hängt die Zeilen mit Präfix an und zeigt nur Namen. Claude liest `secrets.env` nie.

## Begründung
- **Präfix:** Die Newsletter-Dropbox-App ist eine eigene App (App-Folder-Zugriff). Ohne Präfix hätten gleichnamige Werte (`DROPBOX_APP_KEY`, `TELEGRAM_*`, `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY`) andere Dienste überschrieben.
- **Übergangs-Fallback:** Der Code lief während der Umstellung unverändert weiter; Rückfall auf die `.env` blieb möglich.
- **Einzelanführungszeichen in `secrets.env`:** mehrere Cron-Jobs laden die Datei per `source`; so bleiben Sonderzeichen sicher.

## Verworfen
| Alternative | Warum verworfen |
|---|---|
| Namen ohne Präfix übernehmen | Kollisionsgefahr mit anderen Diensten, nicht prüfbar, weil `secrets.env` für Claude gesperrt ist. |
| `.env` behalten, nur Rechte härten | Widerspricht der Regel „nur in `secrets.env`". |
| Eigene `EnvironmentFile` je Dienst unter `/etc/pka/` | Verteilt Geheimnisse auf mehrere Dateien. |

## Gilt unter
- Alle Dienste mit `EnvironmentFile=/etc/pka/secrets.env` sehen **alle** Variablen, nicht nur ihre eigenen (bestehendes Muster, wie `rename-webhook`).
- Nach erfolgreichem Lauf des Timers wird `.env.aus` (die beiseite gelegte `.env`) mit `shred -u` gelöscht, danach der `.env`-Fallback in `envquelle.py` entfernt.
- **Rückgängig:** `.env.aus` zurück nach `.env`, Drop-ins löschen, `daemon-reload`, Restart.
