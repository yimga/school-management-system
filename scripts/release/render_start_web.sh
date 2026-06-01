#!/usr/bin/env bash
set -euo pipefail

# Render web start script.
# Uses config/gunicorn.conf.py so HTTP always binds to 0.0.0.0:PORT for port-scan health checks.

APP_MODULE="${GUNICORN_APP_MODULE:-config.wsgi:application}"
GUNICORN_BIN=".venv/bin/gunicorn"
PYTHON_BIN="${VENV_PYTHON:-.venv/bin/python}"
CONFIG_FILE="config/gunicorn.conf.py"

# Avoid conflicting runtime overrides that can silently switch bind targets.
unset GUNICORN_CMD_ARGS || true

if [[ ! -x "${GUNICORN_BIN}" ]]; then
  GUNICORN_BIN="gunicorn"
fi
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python"
fi

if [[ "${RUN_STARTUP_SCHEMA_CHECK:-1}" == "1" ]]; then
  echo "[web-start] running tenant runtime checks"
  "${PYTHON_BIN}" manage.py check_tenant_runtime
fi

# Ensure PORT is set for config (Render sets it; default for local)
export PORT="${PORT:-10000}"
export WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
export GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
export GUNICORN_WORKER_CLASS="${GUNICORN_WORKER_CLASS:-gthread}"
# Surfaced on /health/ — missing value means Render dashboard overrode startCommand.
export RMC_WEB_START_SCRIPT="render_start_web"
export GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"

# ASGI mode (opt-in via WEB_SERVER_MODE=asgi). Runs the app under uvicorn
# workers so async SSE streams are coroutines, not pinned gthread threads.
# Default stays WSGI/gthread so this is fully reversible — flip the env on a
# staging service first. See docs/ASGI_STREAMING.md.
if [[ "${WEB_SERVER_MODE:-wsgi}" == "asgi" ]]; then
  APP_MODULE="${GUNICORN_ASGI_APP_MODULE:-config.asgi:application}"
  export GUNICORN_WORKER_CLASS="uvicorn.workers.UvicornWorker"
  export RMC_WEB_START_SCRIPT="render_start_web_asgi"
  echo "[web-start] ASGI mode enabled (uvicorn workers; gthread threads ignored)"
fi

echo "[web-start] starting ${APP_MODULE} via ${CONFIG_FILE} (bind 0.0.0.0:${PORT}, workers=${WEB_CONCURRENCY}, threads=${GUNICORN_THREADS}, class=${GUNICORN_WORKER_CLASS}, timeout=${GUNICORN_TIMEOUT})"

exec "${GUNICORN_BIN}" -c "${CONFIG_FILE}" "${APP_MODULE}"
