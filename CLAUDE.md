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

⚠️ **Nach jedem git pull:** `config.json` gehört danach root (git pull als root) → gunicorn (User: webhook) kann nicht schreiben → Einstellungen speichern schlägt mit 500 fehl. Immer `chown webhook:webhook /opt/newsletter-digest/config.json` nach dem Pull ausführen. Bei Deploy über Claude-Remote (`git_pull`-Aktion) passiert das automatisch (siehe `claude-remote-git-pull`-Script im Claude-Remote-Repo); beim manuellen SSH-Deploy oben weiterhin nötig.

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

## Telegram-Digest-Versand (seit 2026-07-24, Kurzfassung seit 2026-08-02)
Bei erfolgreichem Digest sendet `/api/process` (app.py) eine **Kurzfassung** per Telegram (`telegram_digest()` + `build_digest_teaser()`, Präfix 📰). Pro Kategorie: Name, Mail-Anzahl, Anzahl Punkte (Regex-Zählung der Bullet-Zeilen) und die von Claude ohnehin generierte „Relevanz heute"-Zeile als Einzeiler – kein zusätzlicher Claude-Call. Am Ende Link auf die App (`NEWSLETTER_URL`) für die Details. Ersetzt den ursprünglich vollen Inhalt (seit 2026-07-24) – Josef wollte auf Telegram nur eine Zusammenfassung, Details in der App. Gilt für jeden erfolgreichen Lauf inkl. Nachhol-Digest (`--catchup-days`), da beide denselben `/api/process`-Pfad nutzen.

## SW-Cache-Name
`newsletter-v1` – bei Icon/Manifest-Änderungen hochzählen → `newsletter-v2`

## Icon
Lucide newspaper-ähnlich, Hintergrundfarbe `#1e3a5f` (Dunkelblau)
Methode B (cairosvg, server-seitig), generiert in `/opt/newsletter-digest/icons/`

## Config-Schema (config.json)
```json
{
  "schedule": {"type": "weekly|daily|monthly", "weekday": "sunday", "week": 1, "hour": 7, "hours": [7, 18]},
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
- Timer läuft **stündlich**, fetch_mails.py prüft `should_run_today()` → bei `type: "daily"` läuft der Digest zu **jeder** in `schedule.hours` gelisteten Uhrzeit (seit 2026-07-26, beliebig viele, Standard aktuell `[7, 18]` = 2×/Tag). `weekly`/`monthly` weiterhin nur eine `schedule.hour`. Alte configs mit nur `hour` (kein `hours`) werden für `daily` automatisch als Ein-Uhrzeiten-Liste behandelt – kein manuelles Migrieren nötig.
- **Kostenhinweis:** jede zusätzliche tägliche Uhrzeit verdoppelt/vervielfacht die Digest-Erstellungskosten (ein Kategorisierungs-Lauf pro konfigurierter Uhrzeit) – bei `[7, 18]` grob 2× die bisherigen ~$0,20–0,25/Tag. In der PWA unter Einstellungen → Zeitplan → „Täglich" → Uhrzeiten-Liste einstellbar.

## Nachhol-Digest (manuell, bei ausgefallenem Digest)
```bash
ssh root@89.167.104.145
cd /opt/newsletter-digest
venv/bin/python3 fetch_mails.py --catchup-days 14
```
Durchsucht `[Google Mail]/Alle Nachrichten` (nicht INBOX, da ältere Mails ggf. schon archiviert sind) rein lesend, N Tage zurück, umgeht `should_run()`. Schreibt normal `digest_<heute>.json` über denselben `process_mails()`-Pfad inkl. Kosten-Hard-Kill-Schutz. Vor Nutzung sicherstellen, dass Kosten-Tracking aktiv ist (siehe unten) – bei vielen Tagen potenziell teurer als ein normaler Lauf.

## Kosten-Tracking (seit 2026-07-24)
`costs.py` trackt jeden Claude-Call (Kategorie-Zusammenfassung in `app.py` + Auto-Kategorisierung in `fetch_mails.py`) in `claude_costs.json` (gitignored, USD, pro Call + Tag/Woche/Monat/Jahr). Session = ein Kalendertag.
- **1$/Tag:** Telegram-Info, Verarbeitung läuft normal weiter.
- **5$/Tag:** Selbstständiger Abbruch der restlichen Verarbeitung (verbleibende Kategorien/unbekannte Absender werden übersprungen, bereits Fertiges bleibt gespeichert). Kein Warten auf Bestätigung.
- Sichtbar über `/api/costs` + Kosten-Overlay in der PWA (Header-Button neben Einstellungen).
- Details: ADR-004, `PKA/BKM/Claude-API-Kosten-Tracking.md`.

## Dark-/Hell-Modus-Umschalter (v2.12, 2026-08-15)

Manueller Umschalter im Info-Sheet ergänzt (überschreibt `prefers-color-scheme`), Standard-Pattern aus `PKA/BKM/PWA-Standards.md`. `theme-color`-Meta war ohnehin für Light/Dark identisch, daher nur auf ein Tag konsolidiert (kein dynamischer Sync nötig). Kein SW-Cache-Bump nötig (network-first HTML).

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
- **Quellenangabe pro Punkt (seit 2026-07-26):** `call_claude()` übergibt pro Mail die Absender-Domain (`Quelle: {domain}` vor `Betreff:`), System-Prompt weist Claude an, jeden Punkt inline mit `(Quelle: domain.de)` abzuschließen – bewusst **innerhalb** der bestehenden Bullet-Zeile (Teil von `m[2]` im Parser), nicht als eigene Zeile, damit `parseDigestText()` unverändert bleibt (siehe dessen Historie oben). Domain wird simpel per `addr.split("@")[-1]` extrahiert, kein Mapping auf hübsche Markennamen. Noch nicht mit echtem API-Call verifiziert (nur Format-Kompatibilität mit dem Parser lokal simuliert) – beim nächsten echten Digest-Lauf prüfen, ob Claude das Format zuverlässig einhält.
- Nach git pull als root: `chown webhook:webhook /opt/newsletter-digest/config.json` – sonst 500 beim Einstellungen speichern (PermissionError)
- Nach dem Digest-Lauf werden erfolgreich kategorisierte Mails automatisch als gelesen markiert und in `[Google Mail]/Alle Nachrichten` archiviert (aus INBOX entfernt). Unkategorisierte Mails bleiben im INBOX
- **`parseDigestText()`-Regex verwarf praktisch allen Inhalt (behoben 2026-07-24, Bug seit 2026-06-27):** `bold = t.replace(/^[-*]\s*/, '')` sollte einen Bullet-Prefix ("- "/"* ") strippen, matchte als Zeichenklasse `[-*]` aber nur EIN Zeichen – bei führendem `**Titel**` (Claude nutzt nie einen "- "-Prefix) wurde eines der beiden Sternchen abgeschnitten, wodurch die nachfolgende `^\*\*...`-Bold-Erkennung nie mehr traf. Symptom: App zeigte fast keinen Inhalt (Parse-Fallback), Telegram (unverarbeiteter Rohtext) zeigte alles – daher der Eindruck „App-Text stark gekürzt ggü. Telegram". Fix: negativer Lookahead `/^[-*](?!\*)\s*/` verhindert das Stripping vor einem zweiten Sternchen.
- **`parseDigestText()` übersah nummerierte Aufzählungen (behoben 2026-08-02):** Claude formatiert Bullets nicht deterministisch – mal `**Titel**`, mal `- **Titel**`, mal `**1. Titel**` (Nummer innerhalb der Sternchen, rendert noch mit Nummer im Titel), mal `1. **Titel**` (Nummer **vor** den Sternchen). Die alte Regex strippte nur `-`/`*`-Prefixe, nicht `N.`/`N)` – bei diesem letzten Format matchte weder `bold` noch die nachfolgende `^\*\*`-Erkennung, jeder Punkt wurde komplett verworfen (App: „Inhalt konnte nicht geparst werden", Telegram zeigte den Rohtext normal weiter). Fix: `bold = t.replace(/^(?:[-*](?!\*)|\d+[.)])\s*/, '')` strippt jetzt zusätzlich führende `N.`/`N)`-Nummerierung. Gegen alle vier bekannten Formatvarianten getestet (kein echter Browser-Test möglich, `claude-in-chrome`-Extension in der Umgebung nicht verbunden) – bei nächster Gelegenheit im echten Browser gegenprüfen.
- **Pull-to-Refresh-touchend prüfte keine Zugdistanz (Bug seit initialem Commit, zweistufig behoben):** `touchend`-Handler löste bei JEDEM Tap oben auf der Seite (u.a. jeder Tab-Klick) einen vollen Refresh inkl. `renderTabs()` aus. Symptom: Tab-Wechsel (z.B. zu „Finanzen") sprang sofort zurück zu Tab 0 („KI & Tech"), Archiv-Dropdown sprang auf „Aktuell" zurück (weil `loadDigestList()` das `<select>` komplett neu befüllt), teils auch „keine Einträge" durch Race Condition mit einem parallel laufenden `loadDigest()`.
  - **1. Fix (2026-07-24, `c6f811c`):** `touchend` prüft zusätzlich `ptrEl.classList.contains('show')` (ob tatsächlich über die 50px-Schwelle gezogen wurde) – **aber nur mit `curl` verifiziert, nicht auf echtem Gerät getestet** (kein Browser-Tool in der damaligen Umgebung verfügbar), Einschränkung war explizit kommuniziert.
  - **2. Fix (2026-07-26, `df5751c`):** Bug bestand weiter – iOS-Scroll-Bounce (elastisches Überscrollen am Seitenanfang) kann bei einem simplen Tap trotzdem ein `touchmove`-Delta >50px erzeugen, auch ohne echten Pull-Gesture. Root Cause daher nicht die fehlende Distanzprüfung selbst, sondern dass Pull-to-Refresh überhaupt für Taps auf interaktive Elemente „scharf geschaltet" wurde. Fix: `touchstart` armiert `ptrActive` jetzt gar nicht erst, wenn der Touch auf `.tab-btn` oder `#archive-select` startet (`e.target.closest(...)`) – unabhängig von späteren `touchmove`-Deltas kann für diese Elemente kein Pull mehr ausgelöst werden. **Ebenfalls noch nicht auf echtem Gerät verifiziert** – bei erneutem Auftreten dieses Symptoms als Erstes prüfen, ob der Touch wirklich auf `.tab-btn`/`#archive-select` beginnt oder ob es einen dritten, bisher unbekannten Auslöser gibt.
- **Bulk-IMAP-Operationen (>100 Mails) über Sequenznummern sind unzuverlässig:** Beim einmaligen Rückstau-Cleanup (2026-07-24, 310 Mails) brach ein Sequenznummer-basierter `for mid in seen_ids: copy(); store(+Deleted)`-Loop + einmaligem `expunge()` am Ende nach 310 gemeldeten Erfolgen (0 Fehler) nur ~160 Mails wirklich ab – Ursache nicht abschließend geklärt (vermutlich Sequenznummer-Drift bei sehr vielen Operationen in einer Session). Fix: UID-basierte Operationen (`imap.uid('SEARCH', ...)`, `imap.uid('COPY', uid, ...)`, `imap.uid('STORE', uid, '+FLAGS', '(\\Deleted)')`) – UIDs sind stabil und ändern sich nie, im Gegensatz zu Sequenznummern. Bei künftigen Bulk-Operationen (>50 Mails) immer UID-basiert arbeiten, nie Sequenznummern.
- **Gmail-Konto-Sprache ist nicht stabil (Pitfall seit 2026-06-29, zweimal gebrochen):** Mailbox-Namen sind lokalisiert und ändern sich mit der Kontosprache. Ursprünglich lief das Konto auf Deutsch (`[Google Mail]/Alle Nachrichten`, `Gesendet`, `Papierkorb` etc.) – der Archivierungscode nutzte seit Einführung (2026-06-29) fälschlich den englischen Namen → `COPY` schlug seither bei jedem Lauf fehl, `\Seen` wurde aber vorher gesetzt (kein Rollback bei Exception in derselben try-Zeile) → ca. 310 Mails haben sich unarchiviert, aber als gelesen markiert in der INBOX angesammelt, bis der Fix am 2026-07-24 den deutschen Namen hartcodierte. **Zweiter Ausfall (2026-08-19 bis 2026-09-01):** Das Konto lief zwischenzeitlich auf Englisch um (`All Mail` statt `Alle Nachrichten`) – der jetzt hartcodierte deutsche Name brach erneut, `SELECT` schlug 13 Tage lang fehl (kompletter Ausfall des Nachhol-Modus, IMAP-Login selbst war durch ein separates Problem – abgelaufenes App-Passwort – zusätzlich verdeckt). **Endgültiger Fix (2026-09-01):** `find_all_mail_folder()` ermittelt den Ordner jetzt dynamisch über das IMAP-Special-Use-Flag `\All` (`imap.list()` + Regex auf die Flag-Zeile) statt einen Namen zu hardcoden – sprachunabhängig, bricht bei künftigen Kontoeinstellungen nicht mehr. Bei jedem neuen IMAP-Mailbox-Zugriff (`select`/`copy`/etc.) weiterhin den `SELECT`-Rückgabewert prüfen (`typ != "OK"`), nicht stillschweigend ignorieren.
- **Gmail-App-Passwort kann ohne Vorwarnung ablaufen/widerrufen werden:** Löste am 2026-08-19 einen `AUTHENTICATIONFAILED`-Fehler aus, der bis 2026-09-01 unbemerkt blieb (kein Telegram-Alert für IMAP-Login-Fehler im Fetch-Pfad – nur für andere Fehlerpfade). Symptom: `newsletter-fetch.timer` läuft „erfolgreich" durch (Exit 0), aber es entstehen keine Digests mehr – IMAP-Fehler zeigen sich nur im `journalctl`-Log, nicht per Alarm. Neues Passwort unter https://myaccount.google.com/apppasswords generieren, in `/opt/newsletter-digest/.env` (`GMAIL_APP_PASSWORD`) eintragen. Erwägenswert für später: `notify_telegram()` auch im IMAP-Login-Fehlerpfad von `fetch_mails()`/`fetch_from_all_mail()` sicherstellen, damit sowas künftig auffällt statt erst nach Tagen bemerkt zu werden (steht bereits so im Code für `fetch_mails()`, war hier also aktiv – aber offenbar nicht angekommen/übersehen, ggf. Telegram-Zustellung an dem Tag separat prüfen).
- `costs.py`/`_load()`: bei bereits existierender `claude_costs.json` im Alt-Format immer `dict.update(raw)` auf einen Default-Dict, nie `return raw` direkt – sonst `KeyError` auf neue Keys (`calls`/`daily`), live gefunden beim Sentiment-Scanner-Rollout (2026-07-24)
- **Server-Drift-Warnung:** Diese Archivierungsfunktion in `fetch_mails.py` wurde am 2026-06-29 direkt auf dem Server implementiert und erst am 2026-07-24 (bei einem `git pull`-Konflikt) ins Repo zurückgeholt – bis dahin unsynchronisiert. Vor jedem Deploy prüfen (`ssh ... "cd /opt/newsletter-digest && git status"`), ob der Server unerwartete lokale Änderungen an `.py`-Dateien hat (nicht nur `config.json`, das ist normal) – sonst droht stillschweigender Feature-Verlust beim Überschreiben
- **Doppelte `let`-Deklaration bricht das komplette Inline-Script (2026-08-11):** Die Swipe-Navigation (v2.8) deklarierte global `let _cats`, das mit der schon bestehenden Settings-Sheet-Variable gleichen Namens kollidierte – zwei `let`-Deklarationen im selben Scope sind ein JS-Syntaxfehler, der das gesamte `<script>` am Parsen hindert (nicht nur die neue Funktion). `curl`-Checks auf statisches HTML sehen so einen Fehler nicht, da sie nur den HTML-Text prüfen, nicht die JS-Ausführung. Fix: Swipe-Variable zu `_swipeCats` umbenannt (v2.9). Bei künftigen JS-Änderungen in `index.html`: Variablennamen vorab mit `grep -n "let <name>"` auf Kollisionen prüfen, und Syntax nicht nur per `curl`, sondern mit einer echten JS-Engine (z.B. `osascript -l JavaScript -e "$(cat script.js)"` auf macOS) verifizieren.
- **`_set_podcast_status()` sollte bei jedem Statuswechsel den Eintrag ersetzen, nicht mergen:** Erste Version mergte per `entry.update(extra)` – nach einem fehlgeschlagenen Versuch (`status: error`) blieb die alte Fehlermeldung auch nach einem erfolgreichen Retry (`status: done`) im JSON stehen, da `error` nie explizit entfernt wurde. Fix: `data[date_str] = {...}` baut bei jedem Aufruf einen frischen Eintrag.
- **Kategorien-Tab-Leiste (`#tabs-bar`) seit 2026-08-14 fixiert am unteren Bildschirmrand** (Josef-Wunsch, smartphonegerecht – Standard jetzt in `PKA/BKM/PWA-Standards.md` „Tab-Leiste am unteren Bildschirmrand", Variante B/dynamische Tabs). `#archive-bar` (Ausgabe-Dropdown) bleibt bewusst oben im normalen Fluss – nur die Kategorien-Auswahl wanderte nach unten. `#main`-Padding-bottom und `.back-top`-Position wurden entsprechend angepasst, `switchTab()`/Swipe-Logik unverändert (nur Position im DOM/CSS geändert).

## Podcast-Feature (seit 2026-08-11)
Button „Podcast erstellen" pro Digest-Tag erzeugt einen Zwei-Sprecher-Podcast:
- `podcast.py` – neues Modul: `generate_script()` (Claude-Call, System-Prompt für Dialogskript, Antwort als reines JSON-Array `[{"speaker":"A"|"B","text":"..."}]`), `synthesize_audio()` (OpenAI TTS `tts-1`, Stimme `onyx` für Sprecher A männlich / `nova` für Sprecher B weiblich, Zusammenführung per `pydub`), `upload_to_dropbox()`/`download_audio()` (Dropbox SDK, App-Folder-Scope)
- Läuft als Hintergrund-Thread (`threading.Thread`, `daemon=True`) in `app.py`, Status in `data/podcast_status.json` (nicht im Repo, wie `data/` generell)
- Endpoints: `POST /api/podcast/<datum>` (startet Erstellung, 429 bei Tages-Kostenlimit), `GET /api/podcast/<datum>/status` (Polling), `GET /api/podcast/<datum>/audio` (streamt von Dropbox durch, kein Dropbox-Token im Client)
- Fertiges Ergebnis wird zusätzlich als `podcast`-Feld ins `digest_<datum>.json` geschrieben (Quelle der Wahrheit für die App; der Status-File ist nur für laufende Erstellung)
- Kosten: `costs.py` um `record_tts_call()` erweitert (OpenAI tts-1: $0,015/1000 Zeichen), teilt sich Tages-Warn-/Hard-Kill-Schwellen (1$/5$) mit dem bestehenden Claude-Tracking in derselben `claude_costs.json`
- Neue Secrets in `.env`: `OPENAI_API_KEY` (Scope: nur `Text-to-speech (/v1/audio/speech)`, Restricted), `DROPBOX_APP_KEY`/`DROPBOX_APP_SECRET`/`DROPBOX_REFRESH_TOKEN` (eigene Dropbox-App, App-Folder-Scope, nicht der zentrale Token anderer Projekte)
- Server: `dropbox` + `pydub` im venv installiert, `ffmpeg` war schon vorhanden (`/usr/bin/ffmpeg`)
- Verifiziert mit echtem Test-Digest (2026-08-11): Skript-Qualität gut (natürlicher Dialog, keine reine Stichpunkt-Vorlesung), Audio 793KB/~99s MP3 abspielbar, Kosten korrekt getrackt ($0,047 TTS + $0,016 Skript). Erster Testlauf schlug mit 429 fehl, da der neue OpenAI-Account noch keine Credits hatte – nach Aufladung erfolgreich.

## Aktueller Stand
[x] GitHub-Repo angelegt (sEppofaz/Newsletter-Digest)
[x] Server: /opt/newsletter-digest/ angelegt
[x] systemd-Service aktiv (newsletter-digest.service, Port 5006)
[x] systemd-Timer aktiv (newsletter-fetch.timer, stündlich)
[x] nginx-Location aktiv (/newsletter/)
[x] .env auf Server gesetzt (ANTHROPIC_API_KEY, CLAUDE_MODEL, BEARER_TOKEN, TELEGRAM_*, GMAIL_*, OPENAI_API_KEY, DROPBOX_*)
[x] Icon-Berechtigungen gesetzt (chown webhook)
[x] Gmail IMAP aktiviert + App-Passwort generiert (josef.jf.fischer@gmail.com)
[x] Erster Test-Digest manuell erstellt und in PWA gerendert
[x] Auto-Kategorisierung per Claude Haiku (kein manuelles Mapping nötig)
[x] Volle Rubrik-Variabilität: An/Aus, Name, Context, Bullets, Keywords, neue Rubriken
[x] Uhrzeit-Picker in PWA-Einstellungen
[x] Dynamische Tabs aus Config
[x] Double-Opt-In-Mails bestätigt (11 Newsletter)
[x] PWA auf Homescreen installiert
[x] Horizontales Wischen zwischen Rubriken (v2.8/v2.9)
[x] Podcast-Feature: Zwei-Sprecher-TTS, Dropbox-Ablage (v2.9)
