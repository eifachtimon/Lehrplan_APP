# Themen-Übersicht: Lektion per Pointer ziehen

Kurznotiz aus der Implementierung (Mai 2026). Cursor-Regel parallel: `.cursor/rules/thema-lektion-pointer-drag.mdc` (lokal, `.cursor` ist gitignored).

## Architektur

- **Ein Gesten-Stack:** `frontend/src/planning/useThemaLektionPointerDrag.js`
- **Liste:** Umsortieren per Platzhalter (`themaOverviewDnD.js`), kein HTML5-`draggable`
- **Kalender:** `calendarDropFromPointer.js` + `dropLektionOnCalendarAtPointer`
- **Kein** FullCalendar-`Draggable` auf `.thema-lek-card` (Konflikt / `ui`-Fehler)

## Karten-Layout

CSS an `.thema-dashboard__lektionen .thema-lek-card` — nicht an `fc-external-event`.

## Kalender-Vorschau stabil

| Problem | Lösung |
|--------|--------|
| `elementFromPoint` trifft Vorschau | Nur Geometrie; `.cal-event--lek-drag-preview { pointer-events: none }` |
| Springen bei jedem Pixel | Vorschau per FC-API `setDates`, nicht in `events[]`; Update nur bei `calendarSlotKey`-Wechsel (15 min) |
| Spalten flackern | `stickyDate` + Rand-Hysterese am Kalender |

Preview-ID: `LEKTION_DRAG_PREVIEW_EVENT_ID` in `calendarEventResolve.js`.

State: Hook → `ThemaOverviewPanel` → `ThemaWeekCalendarBlock` → `CalendarView` (`lektionDragPreview`).
