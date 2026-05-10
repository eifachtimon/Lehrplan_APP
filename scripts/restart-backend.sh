#!/usr/bin/env bash
# Startet das Flask-Backend neu (Port 5001): beendet einen bestehenden Listener, startet server.py.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
PORT="${PORT:-5001}"

if [[ ! -f "$BACKEND/server.py" ]]; then
  echo "Fehler: server.py nicht gefunden unter $BACKEND" >&2
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "Beende Prozess auf Port $PORT ..."
    kill "$(lsof -t -iTCP:"$PORT" -sTCP:LISTEN)" 2>/dev/null || true
    sleep 1
  fi
fi

cd "$BACKEND"
echo "Starte Backend: $BACKEND/server.py (Port $PORT)"
exec python3 server.py
