#!/usr/bin/env bash
set -euo pipefail

# Render web start script.
# Forces an explicit HTTP bind so port scanning always detects the service.

PORT_VALUE="${PORT:-10000}"
WORKERS_VALUE="${WEB_CONCURRENCY:-2}"
THREADS_VALUE="${GUNICORN_THREADS:-2}"
TIMEOUT_VALUE="${GUNICORN_TIMEOUT:-120}"
APP_MODULE="${GUNICORN_APP_MODULE:-config.wsgi:application}"
GUNICORN_BIN=".venv/bin/gunicorn"

# Avoid conflicting runtime overrides that can silently switch bind targets.
unset GUNICORN_CMD_ARGS || true

if [[ ! -x "${GUNICORN_BIN}" ]]; then
  GUNICORN_BIN="gunicorn"
fi

echo "[web-start] binding ${APP_MODULE} on 0.0.0.0:${PORT_VALUE}"
echo "[web-start] workers=${WORKERS_VALUE} threads=${THREADS_VALUE} timeout=${TIMEOUT_VALUE}"

exec "${GUNICORN_BIN}" "${APP_MODULE}" \
  --bind "0.0.0.0:${PORT_VALUE}" \
  --workers "${WORKERS_VALUE}" \
  --threads "${THREADS_VALUE}" \
  --timeout "${TIMEOUT_VALUE}" \
  --access-logfile "-" \
  --error-logfile "-"
