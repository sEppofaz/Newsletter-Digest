# ADR-006: Podcast-Feature – OpenAI TTS, Dropbox-Ablage, Hintergrund-Thread

**Datum:** 2026-08-11
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

Josef wollte aus jedem Digest einen Zwei-Personen-Podcast erzeugen können (männliche/weibliche Stimme, eine kündigt an, die andere erläutert). Drei offene Architekturfragen: welcher TTS-Anbieter, wo Skript+Audio ablegen, wie mit der Laufzeit umgehen (Skript-Generierung + mehrere TTS-Calls + Upload dauert deutlich länger als ein normaler Digest-Call).

## Entscheidung

- **TTS-Anbieter:** OpenAI TTS (`tts-1`, Stimmen `onyx`/`nova`)
- **Ablage:** Dropbox (eigene App, App-Folder-Scope), sowohl Audio als auch das generierte Skript
- **Laufzeit:** Erstellung läuft in einem Hintergrund-Thread (`threading.Thread(daemon=True)`), Status wird in einer separaten JSON-Datei (`data/podcast_status.json`) getrackt, Frontend pollt per `GET /api/podcast/<datum>/status`

## Begründung

- **OpenAI TTS statt ElevenLabs:** Preisvergleich ergab $0,015/1000 Zeichen (OpenAI Standard) vs. $0,048–0,12/1000 Zeichen (ElevenLabs API) – 4–8× teurer bei vergleichbarer Qualität für diesen Zweck. Bei geschätzten ~12.000 Zeichen/Podcast: ~$0,18 (OpenAI) vs. $0,58–1,44 (ElevenLabs).
- **Skript zusätzlich zu Audio speichern:** ermöglicht Nachvollziehbarkeit/Debugging und spätere Wiederverwendung ohne erneuten kostenpflichtigen Claude-Call, kostet selbst nahezu nichts (reiner Text).
- **Hintergrund-Thread statt synchronem Request:** `newsletter-digest.service` läuft mit Gunicorn-Timeout 120s (siehe Pitfalls in CLAUDE.md); Skript-Generierung + N sequenzielle TTS-Calls + Dropbox-Upload können diese Grenze überschreiten. Ein blockierender Request hätte den Worker riskiert (`WORKER TIMEOUT`), wie es beim Digest selbst schon einmal passiert ist (Pitfall, behoben durch Timeout-Erhöhung – hier wird das Problem stattdessen strukturell vermieden).
- **Datei-basiertes Status-Tracking statt In-Memory-Dict:** funktioniert korrekt unabhängig davon, ob Gunicorn mit einem oder mehreren Worker-Prozessen läuft (In-Memory-State wäre pro Prozess isoliert und für Worker >1 falsch).

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| ElevenLabs statt OpenAI TTS | 4–8× teurer pro Zeichen, Qualitätsvorteil für diesen Zweck nicht ausschlaggebend |
| Nur Audio speichern, kein Skript | Skript kostet quasi nichts extra, aber hoher Nutzen für Debugging/Wiederverwendung |
| Server-Speicherung statt Dropbox | Explizit Josefs Wunsch (Podcasts auf Dropbox verfügbar/synchronisiert haben) |
| Synchroner Request mit erhöhtem Gunicorn-Timeout | Erstellung kann mehrere Minuten dauern (mehrere TTS-Calls + Upload) – ein sehr hoher Timeout-Wert wäre fragil und blockiert einen Worker unnötig lange |
| In-Memory-Status-Dict (global im Flask-Prozess) | Bricht bei mehreren Gunicorn-Workern (jeder Worker hätte eigenen, inkonsistenten Status) |

## Gilt unter

- Podcast-Erstellung bleibt on-demand (Button-Klick), kein automatischer Lauf pro Digest – bei automatischer Erzeugung müsste die Kostenkalkulation neu bewertet werden
- Gunicorn-Timeout bleibt bei 120s oder niedriger (sonst könnte ein synchroner Ansatz wieder infrage kommen)
- Zeicheneinheit-Preismodell von OpenAI TTS bleibt wettbewerbsfähig – bei signifikanten Preisänderungen eines Anbieters ADR erneut prüfen

## Konsequenzen

+ Deutlich günstiger als ElevenLabs-Alternative bei vertretbarer Qualität
+ Skript jederzeit nachvollziehbar/wiederverwendbar
+ Kein Risiko für Gunicorn-Worker-Timeouts, robust auch bei mehreren Workern
- Dritter externer API-Anbieter (OpenAI) neben Anthropic und Dropbox nötig, zusätzlicher Secret-Verwaltungsaufwand
- Status-Polling im Frontend statt sofortiger Antwort – Nutzer sieht Ergebnis erst nach 1–2 Minuten
