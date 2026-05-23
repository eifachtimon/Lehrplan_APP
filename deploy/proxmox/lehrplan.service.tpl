[Unit]
Description=Lehrplan Flask API (Gunicorn)
After=network.target

[Service]
Type=simple
User=@@APP_USER@@
Group=@@APP_USER@@
WorkingDirectory=@@APP_ROOT@@/backend
Environment=PATH=@@APP_ROOT@@/backend/.venv/bin
Environment=CORS_ORIGINS=@@CORS_ORIGINS@@
ExecStart=@@APP_ROOT@@/backend/.venv/bin/gunicorn server:app \
  --bind 127.0.0.1:5001 \
  --workers 1 \
  --threads 4 \
  --timeout 180
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
