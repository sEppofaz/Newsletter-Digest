# ADR-005: Voller Digest-Inhalt per Telegram (ersetzt ARCHITECTURE.md-Vorgabe)

**Datum:** 2026-07-24
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

`ARCHITECTURE.md` (ursprüngliche Planung) legte explizit fest: Telegram nur für Fehler-Alerts, kein Digest-Inhalt. Nach einem Tag mit ausgebliebenem Digest (Gunicorn-Timeout) + Verwirrung über den Zugriffsweg äußerte Josef den Wunsch, den fertigen Digest aktiv per Telegram zu bekommen, statt die PWA aktiv öffnen zu müssen.

## Entscheidung

Neue Funktion `telegram_digest()` (📰-Präfix, gleiche Split-Logik wie `telegram_alert()`/⚠️) sendet nach jedem erfolgreichen `/api/process`-Lauf den **vollständigen Inhalt aller Kategorien** als Telegram-Nachricht(en). Gilt automatisch auch für den Nachhol-Digest-Pfad (`--catchup-days`), da beide denselben Endpoint nutzen.

## Begründung

- Direkter, expliziter Josef-Wunsch nach der Erfahrung mit dem ausgebliebenen Digest.
- Wiederverwendung der bestehenden Split-Logik (>4096 Zeichen) – kein neuer Mechanismus nötig.
- Getrennte Präfixe (📰 vs. ⚠️) halten Erfolgs- und Fehler-Nachrichten optisch unterscheidbar im selben Chat.

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| Kompakte Übersicht + Link zur PWA | Josef wollte explizit den vollen Inhalt, nicht nur einen Teaser |
| Ursprüngliche Vorgabe (nur Fehler-Alerts) beibehalten | Genau das war der Auslöser der Anfrage – reine Fehler-Alerts reichten Josef nicht, er will den Inhalt ohne Extra-Schritt |

## Gilt unter

- Digest-Inhalt bleibt überschaubar genug für Telegram (aktuell 3 Kategorien × ~2000–3200 Zeichen) – bei deutlich mehr/größeren Kategorien könnte die Nachrichtenflut (mehrere Teilnachrichten) unpraktisch werden, dann ggf. auf die verworfene „Kompakt + Link"-Variante zurückkommen.

## Konsequenzen

+ Digest ist ohne aktives Öffnen der PWA sofort sichtbar
- Mehrere Telegram-Nachrichten pro Tag bei vielen/langen Kategorien (Signal-Rauschen möglich, bisher kein Problem)
