#!/usr/bin/env bash
set -euo pipefail

# Render web start script.
# Uses config/gunicorn.conf.py so HTTP always binds to 0.0.0.0:PORT for port-scan health checks.

APP_MODULE="${GUNICORN_APP_MODULE:-config.wsgi:application}"
GUNICORN_BIN=".venv/bin/gunicorn"
CONFIG_FILE="config/gunicorn.conf.py"

# Avoid conflicting runtime overrides that can silently switch bind targets.
unset GUNICORN_CMD_ARGS || true

if [[ ! -x "${GUNICORN_BIN}" ]]; then
  GUNICORN_BIN="gunicorn"
fi

# Ensure PORT is set for config (Render sets it; default for local)
export PORT="${PORT:-10000}"
echo "[web-start] starting ${APP_MODULE} via ${CONFIG_FILE} (bind 0.0.0.0:${PORT})"

exec "${GUNICORN_BIN}" -c "${CONFIG_FILE}" "${APP_MODULE}"
