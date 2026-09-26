# ADR-007: Rubrikwechsel mit Drag-Feedback statt echtem Karussell

**Datum:** 2026-09-26
**Status:** aktiv
**Projekt:** Newsletter Digest

## Problem

Der Wechsel zwischen den Rubriken war ein harter Schnitt: `switchTab()` entfernte die Klasse `active` vom alten und setzte sie auf den neuen Abschnitt, die Sichtbarkeit hängt an `display: none/block`. Beim Wischen gab es bis zum Loslassen überhaupt keine Rückmeldung, danach sprang der Inhalt ohne Übergang um. Josef: „mach beim wischen zwischen den rubriken runder, also mach einen schönen übergang".

Ein „richtiger" Übergang im Sinne eines Karussells (beide Abschnitte gleichzeitig sichtbar, der neue schiebt sich herein während der alte hinausgeht) setzt voraus, dass mindestens zwei Abschnitte gleichzeitig gerendert und nebeneinander positioniert sind. Genau das gibt die aktuelle Struktur nicht her: Alle Abschnitte liegen als Geschwister in `#digest-sections`, sind unterschiedlich hoch und alle außer dem aktiven stehen auf `display: none`.

## Entscheidung

Zweistufiger Übergang ohne Strukturänderung:

1. **Während der Geste:** `#digest-sections` wird als Ganzes per `transform: translateX()` mitgezogen, gedämpft über `tanh` (max. 44px) und mit leicht sinkender Deckkraft. Es bewegt sich also nur der *aktuelle* Inhalt – der nächste ist nicht sichtbar.
2. **Nach dem Loslassen:** Der neue Abschnitt wird sichtbar geschaltet und blendet per `slide+fade` aus der Wischrichtung ein (240ms). Die Richtung leitet `switchTab(btn, dir)` aus dem Tab-Index ab, gilt damit auch für Tab-Klicks.

## Begründung

Die Stufe 1 liefert den taktilen Teil, auf den es beim „rund anfühlen" ankommt – man sieht sofort, dass die Geste erkannt wurde. Die Stufe 2 liefert die räumliche Kontinuität (der Inhalt kommt aus der Richtung, in die man gewischt hat). Zusammen ergibt das den gewünschten Eindruck, ohne die Abschnittsstruktur, die Höhenberechnung oder das Scrollverhalten anzufassen.

Ausschlaggebend war das Verhältnis von Nutzen zu Risiko: Ein Karussell hätte Layout, Scrollposition pro Rubrik, Pull-to-Refresh und die Höhenunterschiede zwischen den Rubriken neu zu lösen gehabt – für einen Effekt, der sich in der Praxis um wenige hundert Millisekunden von der jetzigen Lösung unterscheidet.

## Verworfen

| Alternative | Warum verworfen |
|---|---|
| **Echtes Karussell** (alle Abschnitte nebeneinander in einem Flex-Track, `translateX(-100% * idx)`) | Verlangt gleiche Breite und Nebeneinander-Layout aller Abschnitte. Die Rubriken sind sehr unterschiedlich hoch – der Track wäre so hoch wie die höchste Rubrik, mit entsprechendem Leerraum, oder bräuchte pro Wechsel eine Höhenanimation. Zusätzlich müssten Scrollposition und Pull-to-Refresh pro Abschnitt neu gedacht werden. Deutlich größerer Eingriff als der Anlass hergibt. |
| **Nur Fade, ohne Richtung** | Billiger, aber ohne räumlichen Bezug: Beim Wischen nach links soll der Inhalt spürbar von rechts kommen. Ein reiner Fade fühlt sich bei einer gerichteten Geste falsch an. |
| **Kein Drag-Feedback, nur Animation beim Loslassen** | Die ersten ~200ms der Geste blieben wieder ohne Rückmeldung – genau der Teil, den Josef als „nicht rund" beschrieben hat. |
| **Nachbar-Abschnitt beim Draggen live einblenden** | Würde erfordern, den Nachbarn vorab zu rendern und absolut zu positionieren; bringt faktisch die Karussell-Probleme zurück, nur über einen Umweg. |
| **Fertige Bibliothek (Swiper.js o.ä.)** | Die App ist bewusst eine einzelne, abhängigkeitsfreie HTML-Datei. Eine Bibliothek für einen Übergang wäre unverhältnismäßig. |

## Gilt unter

- Die Abschnitte bleiben Geschwister in `#digest-sections` mit `display: none/block`.
- Die Anzahl der Rubriken bleibt klein genug, dass das Vorab-Rendern kein Thema ist.
- Pull-to-Refresh bleibt auf denselben Touch-Events. **Fällt eine dieser Annahmen weg** – etwa wenn pro Rubrik eine eigene Scrollposition gemerkt werden soll – ist das Karussell erneut zu prüfen.

## Konsequenzen

- **Positiv:** Kein Eingriff in Layout, Höhen oder Scrollverhalten; rein additive CSS-Animation plus ein Touch-Handler. Die Richtung gilt automatisch auch für Tab-Klicks, Klick und Wisch fühlen sich gleich an. `prefers-reduced-motion` schaltet beides ab.
- **Negativ:** Man sieht während der Geste nie den nächsten Abschnitt, nur das Wegziehen des aktuellen – kein „Mitschieben" wie in nativen Pager-Ansichten.
- **Zwei Interferenzen, die dauerhaft zu beachten sind:** Ein gleichzeitiges `scrollTo` mit `behavior: 'smooth'` läuft gegen die Einblendung (deshalb hartes `scrollTo(0,0)`), und nach einem erfolgreichen Wechsel darf der Drag nicht zurückfedern (`resetDrag(false)`), sonst überlagern sich Snap-back und Einblendung.
