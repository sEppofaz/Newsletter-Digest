# ADR-002: Auto-Kategorisierung per Claude statt manuelles Absender-Mapping

**Datum:** 2026-06-27
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

Die ursprüngliche Architektur sah ein manuelles Absender→Kategorie-Mapping vor (E-Mail-Adresse → ki_tech/finanzen/automobil/lokal). Für jeden neuen Newsletter müsste Josef manuell die Absenderadresse eintragen. Das ist wartungsintensiv, besonders da Gmail-Absenderadressen erst nach dem ersten Mail-Eingang bekannt sind.

## Entscheidung

Mails ohne bekannten Absender im Mapping werden automatisch per Claude Haiku kategorisiert. Claude bekommt Absender, Betreff und einen 600-Zeichen-Auszug und gibt eine der vier Kategorien oder „keine" zurück.

Das manuelle Mapping bleibt als optionaler Override erhalten (Performance-Vorteil für bekannte Absender, Override bei Fehlkategorisierung).

## Begründung

- Keinerlei Konfigurationsaufwand für neue Newsletter
- Claude kann inhaltlich kategorisieren (nicht nur nach Adresse)
- Mehrkosten: ~100 Token/Mail, bei 20 Mails/Tag = ~$0.05/Monat (vernachlässigbar)
- Kategorisierungs-Call: max_tokens=20 → sehr schnell, kein nennenswerter Latenz-Overhead

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| Nur manuelles Mapping | Zu wartungsintensiv, Absenderadressen erst nach erstem Eingang bekannt |
| Auto-Discovery UI | Halbautomatisch – besser als manuell, aber immer noch Klick-Aufwand nötig |
| Keyword-Matching (Regex) | Fehleranfällig, Pflege von Regex-Regeln ist ebenfalls Aufwand |

## Gilt unter

- Claude Haiku API ist verfügbar
- Kategorien sind stabil (ki_tech, finanzen, automobil, lokal)
- Mails sind Newsletter (kein Spam, der kategorisiert werden sollte)

## Konsequenzen

+ Vollständig wartungsfreier Betrieb nach Erstinstallation
+ Neue Newsletter werden automatisch erkannt
- Kleiner API-Kostenbeitrag pro unbekanntem Absender
- Claude kann gelegentlich falsch kategorisieren → manuelle Korrektur via Mapping möglich
