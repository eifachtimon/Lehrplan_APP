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
- Für lokale Entwicklung bleibt ohne `.env` der Default (AirPlay auf dem Mac nutzt oft Port 5000):
  - Backend: `http://127.0.0.1:5001`
