#!/usr/bin/env bash
# Proxmox-VM: eine Domain, Nginx + systemd + Gunicorn.
# Auf der VM ausführen (nicht auf dem Mac):
#   cd /opt/lehrplan/Lehrplan_APP && bash deploy/proxmox/deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/deploy.env"

usage() {
  cat <<'EOF'
Usage: deploy/proxmox/deploy.sh [--backend-only] [--frontend-only] [--no-restart]

  --backend-only   Nur Python-venv + systemd
  --frontend-only  Nur npm build
  --no-restart     Kein systemctl/nginx reload

Vorbereitung:
  cp deploy/proxmox/deploy.env.example deploy/proxmox/deploy.env
  # APP_ROOT, APP_USER, DOMAIN, PUBLIC_URL, CORS_ORIGINS anpassen

Cursor (Mac): Remote-SSH → Ordner APP_ROOT öffnen → nach Änderungen:
  sudo systemctl restart lehrplan
EOF
}

BACKEND_ONLY=0
FRONTEND_ONLY=0
NO_RESTART=0
for arg in "$@"; do
  case "$arg" in
    --backend-only) BACKEND_ONLY=1 ;;
    --frontend-only) FRONTEND_ONLY=1 ;;
    --no-restart) NO_RESTART=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unbekanntes Argument: $arg" >&2; usage; exit 1 ;;
  esac
done

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Fehlt: ${ENV_FILE}" >&2
  echo "Kopiere deploy/proxmox/deploy.env.example nach deploy/proxmox/deploy.env" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"

: "${APP_ROOT:?APP_ROOT in deploy.env setzen}"
: "${APP_USER:?APP_USER in deploy.env setzen}"
: "${DOMAIN:?DOMAIN in deploy.env setzen}"
: "${PUBLIC_URL:?PUBLIC_URL in deploy.env setzen}"
: "${CORS_ORIGINS:?CORS_ORIGINS in deploy.env setzen}"

PUBLIC_URL="${PUBLIC_URL%/}"

if [[ "${APP_ROOT}" != "${REPO_ROOT}" ]]; then
  echo "Hinweis: APP_ROOT=${APP_ROOT}, Repo liegt unter ${REPO_ROOT}" >&2
  echo "APP_ROOT sollte auf den Repo-Pfad zeigen." >&2
fi

render_template() {
  local src="$1"
  local dest="$2"
  sed \
    -e "s|@@APP_ROOT@@|${APP_ROOT}|g" \
    -e "s|@@APP_USER@@|${APP_USER}|g" \
    -e "s|@@DOMAIN@@|${DOMAIN}|g" \
    -e "s|@@CORS_ORIGINS@@|${CORS_ORIGINS}|g" \
    "${src}" > "${dest}"
}

install_backend() {
  echo "==> Backend (venv + Abhängigkeiten)"
  cd "${APP_ROOT}/backend"
  if [[ ! -d .venv ]]; then
    python3 -m venv .venv
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -U pip
  pip install -r requirements.txt

  if [[ "${EUID}" -eq 0 ]] || command -v sudo >/dev/null 2>&1; then
    local unit_tmp
    unit_tmp="$(mktemp)"
    render_template "${SCRIPT_DIR}/lehrplan.service.tpl" "${unit_tmp}"
    if [[ "${EUID}" -eq 0 ]]; then
      cp "${unit_tmp}" /etc/systemd/system/lehrplan.service
    else
      sudo cp "${unit_tmp}" /etc/systemd/system/lehrplan.service
    fi
    rm -f "${unit_tmp}"
    if [[ "${EUID}" -eq 0 ]]; then
      systemctl daemon-reload
      systemctl enable lehrplan
    else
      sudo systemctl daemon-reload
      sudo systemctl enable lehrplan
    fi
  else
    echo "Warnung: kein sudo — systemd-Unit nicht installiert." >&2
  fi
}

install_frontend() {
  echo "==> Frontend (build, API=${PUBLIC_URL})"
  cd "${APP_ROOT}/frontend"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
  REACT_APP_API_BASE_URL="${PUBLIC_URL}" npm run build
}

install_nginx() {
  if [[ "${EUID}" -ne 0 ]] && ! command -v sudo >/dev/null 2>&1; then
    echo "Warnung: kein sudo — Nginx-Config nicht installiert." >&2
    return
  fi
  echo "==> Nginx"
  local ngx_tmp
  ngx_tmp="$(mktemp)"
  render_template "${SCRIPT_DIR}/nginx-lehrplan.conf.tpl" "${ngx_tmp}"
  if [[ "${EUID}" -eq 0 ]]; then
    cp "${ngx_tmp}" "/etc/nginx/sites-available/lehrplan"
    ln -sf /etc/nginx/sites-available/lehrplan /etc/nginx/sites-enabled/lehrplan
    nginx -t
  else
    sudo cp "${ngx_tmp}" "/etc/nginx/sites-available/lehrplan"
    sudo ln -sf /etc/nginx/sites-available/lehrplan /etc/nginx/sites-enabled/lehrplan
    sudo nginx -t
  fi
  rm -f "${ngx_tmp}"
}

restart_services() {
  [[ "${NO_RESTART}" -eq 1 ]] && return
  if [[ "${EUID}" -eq 0 ]]; then
    systemctl restart lehrplan || systemctl start lehrplan
    systemctl reload nginx
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl restart lehrplan || sudo systemctl start lehrplan
    sudo systemctl reload nginx
  fi
}

run_checks() {
  echo "==> Healthcheck"
  sleep 2
  if curl -sf "http://127.0.0.1:5001/health" | grep -q '"ok"'; then
    echo "Gunicorn: OK (127.0.0.1:5001/health)"
  else
    echo "Gunicorn: noch nicht OK — journalctl -u lehrplan -n 50" >&2
  fi
  if curl -sf -H "Host: ${DOMAIN}" "http://127.0.0.1/health" | grep -q '"ok"'; then
    echo "Nginx-Proxy: OK (Host: ${DOMAIN})"
  else
    echo "Nginx-Proxy: prüfen (DNS/Host-Header oder default_server)" >&2
  fi
  echo ""
  echo "Fertig. Browser: ${PUBLIC_URL}"
  echo "Cursor: Remote-SSH → ${APP_ROOT}"
  echo "Nach Backend-Änderung: sudo systemctl restart lehrplan"
  echo "Nach Frontend-Änderung: bash deploy/proxmox/deploy.sh --frontend-only"
}

if [[ "${FRONTEND_ONLY}" -eq 1 ]]; then
  install_frontend
  restart_services
  exit 0
fi

if [[ "${BACKEND_ONLY}" -eq 1 ]]; then
  install_backend
  restart_services
  run_checks
  exit 0
fi

install_backend
install_frontend
install_nginx
restart_services
run_checks
