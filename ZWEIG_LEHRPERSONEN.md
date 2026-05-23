# Zweig: Planung & Lehrpersonen (in Lehrplan_APP)

Planung, Stundenentwurf und künftige KI-Entlastung leben **im gleichen Frontend** wie die LP21-Suche — nicht in einem separaten CRA auf Port 3003.

## Frontend-Routen (`frontend/`, Port 3002)

| Route | Inhalt |
|-------|--------|
| `/` | LP21-Suche (bestehendes Verhalten) |
| `/kette/:uid` | Aufbau-Kette; URL wird beim Öffnen der Kette gesetzt |
| `/landkarte` | Landkarte-Explorer (Vollbild-Overlay) |
| `/planung/entwurf` | Stundenentwurf — Phase-1-Skelett (Query: `uid`, `code`, `fach`, `text`) |

Konfiguration aller internen Pfade: `frontend/src/config/appUrls.js`  
Navigation: globale Seitenleiste `frontend/src/shell/AppSidebar.js`, `PlanningLocationBar.js`, `docs/SIDEBAR_IA.md`, `docs/NAVIGATION_IA.md`

## Lokal starten

```bash
cd backend && python3 server.py    # Port 5001
cd frontend && npm start             # Port 3002 → http://localhost:3002
```

## Backend (später)

Neue API-Routen für KI/Planung: künftig unter `backend/` (z. B. `/api/planning/*`).  
Phase 1: **kein** KI-Endpoint — nur UI-Skelett auf `/planung/entwurf`.

## Historischer Ordner Lehrpersonen_App

Der Ordner `/Users/timon/Desktop/Development/Lehrpersonen_App` ist **nicht** an GitHub angebunden und wird für Deploy/Entwicklung **nicht** mehr genutzt. Referenzdokumentation kann dort verbleiben; die aktive Implementierung ist **Lehrplan_APP**.
