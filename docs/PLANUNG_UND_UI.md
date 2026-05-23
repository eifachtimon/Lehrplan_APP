# Planung, Themen-UI und lokale Entwicklung

Stand: Mai 2026

## Begriffe in der Oberfläche

- In der UI heißen Planungseinheiten **Thema / Themen** (früher «Vorhaben»).
- Technische IDs, Routen und Store-Felder bleiben vorerst `vorhaben` (z. B. `/planung/vorhaben/:id`).

## Mein Unterricht (Hub)

- **Weiter planen**, **Kalender**, **+ Neu** für schnelle Aktionen.
- **Demo-Daten**: lädt drei Beispiel-Themen (Mathematik, Deutsch, NMG) inkl. Kalendertermine, Erinnerungen, Todos und Notizen. URL-Shortcut: `?demo=1` auf der Hub-Route.
- Tages-Todos und Notizen für «heute» bleiben am Hub.

## Themen-Detailseite

Vier Ebenen: **Überblick** (Grobplanung), **Zwischenziele** (2-Wochen), **Woche**, **Lektion**.

- **Hero** mit Titel, Fach/Zyklus/Klasse (Fach-Chip mit Fachfarbe).
- **Sticky Toolbar** mit Ebenen-Navigation und «Nächster Schritt».
- **Hauptspalte**: Panel-Inhalt in `ThemaPanelShell` / `PlanningSection`.
- **Nebenspalte**: Kompetenzen, Bericht→Struktur, Hinweise, FHNW-Referenz.
- **Woche**: Erinnerungen & To-dos (`WocheErinnerungen`) — gruppiert nach «Heute», «Weitere offen», «Erledigt»; optional an Kalenderwoche gebunden.

## Fach-Farben

- **Mathematik**: Rot-Töne, **Deutsch**: Blau, **NMG**: Grün (weitere Fächer mit Fallback).
- Kalender: Hintergrund heller Schattierung pro Thema innerhalb eines Fachs; Rand/Akzent in Basis-Fachfarbe.
- Implementierung: `frontend/src/planning/fachColors.js`, `fachColors.css`.

## Kalender

- Termine aus Planung und Stundenplan; Filter nach Thema/Fach.
- Fach-Styling über `calendarEventStyles.js` und `planningEvents.js`.

## Lokale Entwicklung

| Dienst   | Befehl              | URL                          |
|----------|---------------------|------------------------------|
| Backend  | `cd backend && python3 server.py` | `http://127.0.0.1:5001` |
| Frontend | `cd frontend && npm start`        | `http://localhost:3002` |

- Health-Check: `curl -s http://127.0.0.1:5001/health` → `{"status":"ok"}`
- Im Dev: `REACT_APP_API_BASE_URL=http://127.0.0.1:5001` in `frontend/.env.development`
- **Nicht** Port 3000 nutzen (macOS/AirPlay-Konflikt → oft HTTP 403).

## Deployment (Proxmox)

Skripte und Vorlagen unter `deploy/proxmox/`:

- `deploy.env.example` — Variablen-Vorlage (echte `deploy.env` nicht committen).
- `deploy.sh`, `lehrplan.service.tpl`, `nginx-lehrplan.conf.tpl`

## Backend-Ergänzungen

- `calendar_feed.py`, `calendar_ics.py` — ICS/Feed-Unterstützung (siehe `server.py`).
- Zweig Lehrende: `ZWEIG_LEHRPERSONEN.md` im Repo-Root.
