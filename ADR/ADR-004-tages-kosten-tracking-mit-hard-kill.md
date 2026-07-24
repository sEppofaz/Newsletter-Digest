# ADR-004: Tages-Kosten-Tracking mit Hard-Kill bei 5$

**Datum:** 2026-07-24
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

Es gab kein Tracking der Claude-API-Kosten und keine Sicherheitsschwelle. Ein Fehler in der Konfiguration, ein Endlos-Loop oder ein extrem großer Nachhol-Lauf (z.B. mehrwöchiger Mail-Rückstand) hätte unbemerkt hohe Kosten verursachen können, bevor jemand es bemerkt.

## Entscheidung

Jeder Claude-API-Call (Kategorie-Zusammenfassung in `app.py`, Auto-Kategorisierung in `fetch_mails.py`) wird über `costs.py` in `claude_costs.json` erfasst (Tokens, Kosten, Zeitstempel, Kontext). Zwei Tages-Schwellen (Session = ein Kalendertag):
- **1$/Tag:** Telegram-Info, Verarbeitung läuft normal weiter.
- **5$/Tag:** Sofortiger, selbstständiger Abbruch der restlichen Verarbeitung (verbleibende Kategorien/unbekannte Absender werden für diesen Lauf übersprungen, bereits fertige Ergebnisse bleiben erhalten). Kein Warten auf manuelle Bestätigung.

Kosten werden direkt in USD geführt (keine EUR-Umrechnung). Sichtbar über neuen `/api/costs`-Endpoint + Kosten-Overlay in der PWA.

## Begründung

- USD ist die native Abrechnungswährung der Anthropic-API – ein Wechselkurs wäre eine zusätzliche, unnötige Fehlerquelle.
- Ein Kalendertag als Session-Grenze ist für Josef intuitiv nachvollziehbar und deckt sich mit dem täglichen Digest-Rhythmus.
- Selbstständiger Abbruch statt Rückfrage: Bei einem echten Kostenausreißer soll das System sofort reagieren, nicht auf eine Telegram-Antwort warten (die verzögert eintreffen oder ausbleiben könnte).
- `claude_costs.json` liegt außerhalb von `config.json`, da letztere per `git pull` überschrieben wird (Merge-Konflikt-Risiko).

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| EUR-Tracking mit Wechselkurs | Zusätzliche Pflege (Kurs veraltet), unnötig da Abrechnung in USD erfolgt |
| Bei 1$ pausieren + auf Telegram-Bestätigung warten | Würde einen blockierenden Wartemechanismus im Flask-Prozess erfordern (Gunicorn-Timeout-Risiko), Josef hat sich explizit für "informieren, nicht warten" entschieden |
| Kosten-Schwellen in `config.json` konfigurierbar | Risiko von Merge-Konflikten beim Server-Deploy, Konstanten im Code sind für dieses Volumen ausreichend |
| Gemeinsames Python-Package für alle Claude-Projekte | Jedes Projekt ist ein eigenständiges Repo/venv auf dem Server – kein Cross-Repo-Import möglich, daher Copy-Paste-Template (siehe `PKA/BKM/Claude-API-Kosten-Tracking.md`) |

## Gilt unter

- Newsletter Digest ruft ausschließlich Claude Haiku 4.5 auf (ein Modell, eine Preistabelle)
- Server-Systemzeit bestimmt die Tagesgrenze (Europe/Berlin)

## Konsequenzen

+ Kostenausreißer werden spätestens bei 5$/Tag automatisch gestoppt
+ Vollständige Kostenhistorie pro Call + aggregiert nach Woche/Monat/Jahr in der PWA einsehbar
- Bei Hard-Kill bleiben Kategorien/Absender für den Tag unbearbeitet (werden ggf. im nächsten Lauf nachgeholt, sofern noch ungelesen)
