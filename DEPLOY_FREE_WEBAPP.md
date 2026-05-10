# Kostenlos als Web-App deployen

Diese Anleitung nutzt:
- Frontend: Vercel (kostenlos)
- Backend: Render (kostenlos)

## 1) Backend auf Render deployen

1. Repo bei GitHub pushen (falls noch nicht aktuell).
2. Auf [Render](https://render.com/) einloggen.
3. `New +` -> `Blueprint`.
4. Dein Repo auswählen.
5. Render liest `backend/render.yaml` ein.
6. Service erstellen.
7. Nach dem ersten Deploy die URL notieren, z. B.:
   - `https://lehrplan-app-backend.onrender.com`
8. Healthcheck testen:
   - `https://.../health` -> sollte `{"status":"ok"}` liefern.

## 2) Frontend auf Vercel deployen

1. Auf [Vercel](https://vercel.com/) einloggen.
2. `Add New` -> `Project`.
3. Das `frontend`-Repo importieren.
4. In Project Settings -> Environment Variables:
   - `REACT_APP_API_BASE_URL=https://dein-backend.onrender.com`
5. Deploy starten.

## 3) CORS korrekt setzen

Im Render-Service (Backend) unter Environment:
- `CORS_ORIGINS=https://dein-frontend.vercel.app`

Bei mehreren Domains:
- `CORS_ORIGINS=https://dein-frontend.vercel.app,https://deine-custom-domain.ch`

## 4) Hinweise

- Der erste Request auf Render Free kann durch Cold Start langsam sein.
- Das Modell wird beim Start geladen; der erste Suchaufruf dauert deshalb länger.
- **macOS:** Nicht nur Port 5000 — **3000** kann mit **AirTunes/AirPlay** kollidieren. Symptom: `POST` auf die App liefert **HTTP 403** und Response-Header `server: AirTunes/...`, obwohl `GET /` noch „normal“ wirkt. Lösung: in `frontend/.env.development` z. B. **`PORT=3002`** setzen und **`npm start` neu starten**; die mitgelieferte Datei nutzt zudem **`REACT_APP_API_BASE_URL=http://127.0.0.1:5001`**, damit die Suche **direkt** Flask trifft.
- Backend lokal: `http://127.0.0.1:5001`

## Lokale Entwicklung – Fehlerdiagnose (Stand Checks)

### Schnelltest im Terminal

```bash
curl -s http://127.0.0.1:5001/health
```

Erwartung: `{"status":"ok"}`. Wenn hier schon gar keine Verbindung besteht oder ein anderer Status als 200 kommt, läuft auf Port **5001** nicht die Flask-App aus `backend/server.py`.

### Symptome und typische Ursachen

| Symptom | Typische Ursache |
|--------|-------------------|
| **Failed to fetch** / Netzwerkfehler | Backend nicht gestartet oder falscher Port; nach Änderungen an `.env` **`npm start` neu starten**. |
| **HTTP 403** auf `/search` (manchmal Header `server: AirTunes/...`) | Auf dem **Mac** oft **Port 3000** (AirPlay/AirTunes) statt des CRA-Servers. **Anderen `PORT` wählen** (siehe `frontend/.env.development`) und Dev-Server neu starten. Wenn 403 **direkt** auf `http://127.0.0.1:5001` → prüfen, ob dort wirklich Flask läuft: `curl -s http://127.0.0.1:5001/health`. |
| Proxy / gleiche Origin | Standard lokal: **`REACT_APP_API_BASE_URL=http://127.0.0.1:5001`** (direkt Flask). Ohne diese Variable nutzt der Dev-Server optional `src/setupProxy.js`; Ziel überschreiben: `PROXY_TARGET=…`. |

### Backend lokal starten

```bash
cd backend && python3 server.py
```

(Standardport **5001**, siehe `server.py`.)

**„Address already in use“ / Port 5001 belegt:** Es läuft schon eine Flask-Instanz (oder ein anderer Prozess). Entweder diese eine nutzen (`curl …/health` testen) oder beenden und neu starten:

```bash
lsof -nP -iTCP:5001 -sTCP:LISTEN
kill $(lsof -ti :5001)   # nur wenn ihr wisst, dass es euer altes server.py ist
```

### Frontend (`npm start`)

- **`npm start`** bindet den CRA-Dev-Server fest an **Port 3002** (siehe `frontend/package.json`). Im Browser **`http://localhost:3002`** öffnen — nicht `:3000`, sonst weiterhin 403/rätselhafte Antworten.
- Alten Dev-Server auf 3000 beenden (Terminal-Fenster mit laufendem `npm start` / Prozess `node` beenden), dann `npm start` neu ausführen.

### Verifiziert (Entwicklungsumgebung)

- `GET /health` → 200, JSON `{"status":"ok"}`.
- `POST /search` mit gültigem JSON → 200, Suchergebnisse (JSON mit `documents`, `metadatas`, …).
