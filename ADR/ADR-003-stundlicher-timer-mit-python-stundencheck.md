# ADR-003: Stündlicher systemd-Timer mit Python-Stundencheck statt Fixed-Time-Timer

**Datum:** 2026-06-27
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

Die konfigurierbare Scan-Uhrzeit (PWA-Einstellung) ließ sich nicht mit einem Fixed-Time systemd-Timer (`OnCalendar=*-*-* 07:00:00`) kombinieren: Eine Änderung der Uhrzeit in der PWA würde keine Wirkung haben, da der Timer unabhängig von `config.json` läuft.

## Entscheidung

Der systemd-Timer läuft **stündlich** (`OnCalendar=hourly`). `fetch_mails.py` fragt via `GET /api/should_run` ob der aktuelle Zeitpunkt stimmt – Flask vergleicht `datetime.now().hour == schedule.get("hour", 7)`.

## Begründung

- Uhrzeit ist in `config.json` gespeichert und per PWA einstellbar, ohne Root-Zugriff auf den Server
- Kein zusätzlicher Mechanismus (z.B. systemctl edit) nötig um den Timer anzupassen
- Stündlicher Tick hat minimalen Overhead (fetch_mails.py läuft in Sekunden durch wenn `should_run()` False zurückgibt)
- Konsistent mit der bestehenden `should_run_today()`-Logik (Wochentag/Monatswoche)

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| Fixed-Time Timer (`07:00:00`) | Uhrzeit nicht per PWA änderbar ohne Root-SSH |
| systemd drop-in override bei Uhrzeit-Änderung | Erfordert Root-Zugriff; komplexe Server-seitige Logik |
| Cron-basierter Timer | Kein Mehrwert gegenüber systemd; schlechtere Integration |

## Gilt unter

- Solange die Uhrzeit mit Stunden-Granularität (nicht Minuten) ausreicht
- Solange der Server keine Hunderte gleichzeitiger OneShot-Services startet

## Konsequenzen

- (+) Uhrzeit frei in PWA konfigurierbar ohne Server-Eingriff
- (+) Ein Code-Pfad für die gesamte Zeitplan-Logik (Flask `should_run_today()`)
- (-) Timer feuert jede Stunde; fetch_mails.py startet kurz und bricht sofort ab wenn nicht der richtige Zeitpunkt
- (-) Granularität auf Stunden begrenzt (kein „09:30 Uhr")
