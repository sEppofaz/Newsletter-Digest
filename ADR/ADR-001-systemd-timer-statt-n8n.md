# ADR-001: systemd-Timer statt n8n für Mail-Fetch-Orchestrierung

**Datum:** 2026-06-27
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

Die ursprüngliche Architektur (ARCHITECTURE.md) sah n8n als Workflow-Engine vor. n8n war laut Annahme „bereits auf dem VPS installiert" – bei Umsetzung stellte sich heraus, dass dies nicht der Fall ist.

## Entscheidung

Kein n8n. Stattdessen: `fetch_mails.py` (Python-Script) + `newsletter-fetch.service` (systemd OneShot) + `newsletter-fetch.timer` (täglich 07:00).

## Begründung

- n8n nicht installiert (≈ 400 MB + Node.js-Overhead wäre nötig gewesen)
- Kein offener Web-Port für n8n-UI erforderlich
- Python passt zum bestehenden Stack (alle Services laufen in Python/Flask)
- systemd-Timer ist wartungsärmer, restartfähig und loggbar via `journalctl`
- Gleiche Funktionalität mit deutlich weniger Abhängigkeiten

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| n8n installieren | ~400 MB Overhead, Node.js-Abhängigkeit, Web-UI-Port, nicht im bestehenden Stack |
| Cron-Job direkt | systemd-Timer ist besser integriert (Logging, Fehlerbehandlung, `Persistent=true`) |

## Gilt unter

- Der Server bleibt Ubuntu-basiert mit systemd
- Die Anzahl der Mails pro Tag bleibt überschaubar (kein Throughput-Problem)

## Konsequenzen

+ Kein n8n-Setup nötig, sofort deploybar
+ Vollständige Logs via `journalctl -u newsletter-fetch`
- n8n-Workflows (falls Josef sie für andere Zwecke nutzen will) müssen separat nachinstalliert werden
- Workflow-Logik liegt im Python-Script, keine visuelle n8n-Darstellung
