#!/usr/bin/env bash
# UX visual QA: Django runserver + Playwright tests/e2e/ux-visual-qa.spec.js
# Optional env: VISUAL_QA_PYTHON (else .venv/bin/python, else python on PATH);
#   VISUAL_QA_SERVER_READY_PATH (default /migrate/), VISUAL_QA_SERVER_READY_MAX_ATTEMPTS, VISUAL_QA_SERVER_READY_SLEEP.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8010}"
PUBLIC_HOST="${VISUAL_QA_PUBLIC_HOST:-runmycampus.com}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/visual-qa}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"

export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"
# Tenant portal Playwright logins (teacher1 / Parent1) use same password as seed_render_users when set
export VISUAL_QA_TENANT_PASSWORD="${VISUAL_QA_TENANT_PASSWORD:-${ADMIN_PASSWORD:-}}"

mkdir -p "$ARTIFACT_DIR"

if ! command -v node >/dev/null 2>&1; then
  echo "run_visual_qa: node is required." >&2
  exit 1
fi

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_visual_qa: Playwright dependencies are missing. Run 'npm ci' first." >&2
  exit 1
fi

SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT

"${PYTHON_CMD}" - <<'PY'
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["VISUAL_QA_USERNAME"]
password = os.environ["VISUAL_QA_PASSWORD"]

user, _ = User.objects.get_or_create(
    username=username,
    defaults={
        "email": f"{username}@example.com",
        "role": "ADMIN",
        "is_staff": True,
        "is_superuser": True,
    },
)
user.email = f"{username}@example.com"
user.role = "ADMIN"
user.is_staff = True
user.is_superuser = True
user.set_password(password)
user.password_strength_score = 100
user.save()

# Optional: when VISUAL_QA_TOTP_HEX is set, seed a confirmed TOTP device so the
# Playwright login helper can satisfy the always-on MFA baseline for ADMIN
# (apps/accounts/mfa_defaults.py) by computing codes from the same hex key.
# Absent the env, MFA is left to the environment (e.g. CI) — unchanged behavior.
_totp_hex = (os.environ.get("VISUAL_QA_TOTP_HEX") or "").strip()
if _totp_hex:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    TOTPDevice.objects.filter(user=user).delete()
    # Wide tolerance (±N 30s windows) so a code stays valid even when a slow dev
    # server takes longer than one window to process the verify POST — otherwise
    # the code "expires in transit" under load and the login loops on rejection.
    # last_t still blocks true replay; this only widens the acceptance window.
    TOTPDevice.objects.create(
        user=user,
        name="visualqa",
        key=_totp_hex,
        step=30,
        digits=6,
        tolerance=30,
        confirmed=True,
    )
    print(f"visual_qa: seeded confirmed TOTP device for {username}")
PY

"${PYTHON_CMD}" - <<PY
import socket
import sys

port = int("$PORT")
sock = socket.socket()
try:
    sock.bind(("127.0.0.1", port))
except OSError:
    print(f"run_visual_qa: port {port} is already in use.", file=sys.stderr)
    sys.exit(1)
finally:
    sock.close()
PY

# Resolve tenant host before runserver so CSRF_TRUSTED_ORIGINS includes the Playwright tenant origin
# (Postgres + django-tenants). SQLite leaves the file empty — tenant portal tests skip in the spec.
export TENANT_DOMAIN_FILE="${ARTIFACT_DIR}/tenant_domain_for_qa.txt"
python - <<PY
import os
import sys
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.db import connection
path = (os.environ.get("TENANT_DOMAIN_FILE") or "").strip()
if not path:
    sys.exit(0)
if connection.vendor != "postgresql":
    open(path, "w", encoding="utf-8").write("")
    sys.exit(0)
try:
    from apps.customers.models import Client, Domain
except Exception:
    open(path, "w", encoding="utf-8").write("")
    sys.exit(0)
c = Client.objects.exclude(schema_name="public").order_by("id").first()
if not c:
    open(path, "w", encoding="utf-8").write("")
    sys.exit(0)
d = Domain.objects.filter(tenant=c).order_by("id").values_list("domain", flat=True).first()
open(path, "w", encoding="utf-8").write((d or "").strip())
PY

TENANT_DOMAIN="$(tr -d '\r\n' <"$TENANT_DOMAIN_FILE" 2>/dev/null || true)"
CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${PUBLIC_HOST}:${PORT},http://${MANAGER_HOST}:${PORT}"
if [[ -n "$TENANT_DOMAIN" ]]; then
  CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS},http://${TENANT_DOMAIN}:${PORT}"
fi

READY_PATH="${VISUAL_QA_SERVER_READY_PATH:-/migrate/}"
READY_MAX="${VISUAL_QA_SERVER_READY_MAX_ATTEMPTS:-60}"
READY_SLEEP="${VISUAL_QA_SERVER_READY_SLEEP:-2}"

# Server backend selection.
# Django's dev runserver (single process, threaded, SQLite) degrades under a
# long sustained browser sweep — requests pile up on threads/locks until it
# stops accepting connections (the documented SSE thread-starvation failure
# mode), and on Windows the process additionally dies on the broken pipe from
# the readiness probe. gunicorn (prefork, multi-worker) is far more robust under
# the sweep and is what production runs, so prefer it whenever it's usable.
#
# gunicorn relies on fork() and does NOT run on native Windows (MSYS/MinGW/
# Cygwin bash), so there we fall back to runserver. Override either way with
# VISUAL_QA_SERVER=gunicorn|runserver.
_uname="$(uname -s 2>/dev/null || echo unknown)"
case "$_uname" in
  MINGW* | MSYS* | CYGWIN* | Windows_NT) IS_WINDOWS=1 ;;
  *) IS_WINDOWS=0 ;;
esac

if [[ -n "${VISUAL_QA_SERVER:-}" ]]; then
  SERVER_KIND="$VISUAL_QA_SERVER"
elif [[ "$IS_WINDOWS" -eq 0 ]] && "$PYTHON_CMD" -m gunicorn --version >/dev/null 2>&1; then
  SERVER_KIND="gunicorn"
else
  SERVER_KIND="runserver"
fi
echo "[run_visual_qa] Server backend: ${SERVER_KIND} (uname=${_uname})."

# Per-viewport cycle: a FRESH server comfortably survives one viewport group's
# ~5 min of load, so we cycle the server per viewport instead of asking one
# process to last ~17 min. The restart is cheap.
stop_server() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" >/dev/null 2>&1 || true
  fi
  SERVER_PID=""
}

start_server() {
  if [[ "$SERVER_KIND" == "gunicorn" ]]; then
    nohup env \
      SECURE_SSL_REDIRECT=0 \
      DEBUG=1 \
      DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings}" \
      DB_LOG_LEVEL="${VISUAL_QA_DB_LOG_LEVEL:-WARNING}" \
      CSRF_TRUSTED_ORIGINS="$CSRF_TRUSTED_ORIGINS" \
      VISUAL_QA_USERNAME="$VISUAL_USERNAME" \
      VISUAL_QA_PASSWORD="$VISUAL_PASSWORD" \
      "$PYTHON_CMD" -m gunicorn config.wsgi:application \
        --bind "127.0.0.1:${PORT}" \
        --workers "${VISUAL_QA_GUNICORN_WORKERS:-2}" \
        --threads "${VISUAL_QA_GUNICORN_THREADS:-4}" \
        --timeout "${VISUAL_QA_GUNICORN_TIMEOUT:-120}" \
        --graceful-timeout 30 \
        --access-logfile - --error-logfile - >"$RUNSERVER_LOG" 2>&1 &
  else
    nohup env \
      SECURE_SSL_REDIRECT=0 \
      DEBUG=1 \
      DB_LOG_LEVEL="${VISUAL_QA_DB_LOG_LEVEL:-WARNING}" \
      CSRF_TRUSTED_ORIGINS="$CSRF_TRUSTED_ORIGINS" \
      VISUAL_QA_USERNAME="$VISUAL_USERNAME" \
      VISUAL_QA_PASSWORD="$VISUAL_PASSWORD" \
      "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
  fi
  SERVER_PID="$!"

  local code=""
  for _ in $(seq 1 "$READY_MAX"); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "http://127.0.0.1:${PORT}${READY_PATH}" || true)"
    if [[ "$code" == "200" ]]; then
      return 0
    fi
    sleep "$READY_SLEEP"
  done
  echo "run_visual_qa: server failed to become ready on port ${PORT} (last HTTP ${code:-none} for ${READY_PATH})." >&2
  tail -n 80 "$RUNSERVER_LOG" >&2 || true
  return 1
}

export TEST_USERNAME="$VISUAL_USERNAME"
export TEST_PASSWORD="$VISUAL_PASSWORD"
export BASE_URL="http://127.0.0.1:${PORT}"
export PUBLIC_BASE_URL="http://${PUBLIC_HOST}:${PORT}"
export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"

# TENANT_DOMAIN / TENANT_DOMAIN_FILE were resolved before runserver (CSRF origins).
TENANT_DOMAIN="$(tr -d '\r\n' <"$TENANT_DOMAIN_FILE" 2>/dev/null || true)"
RULES="MAP ${PUBLIC_HOST} 127.0.0.1,MAP ${MANAGER_HOST} 127.0.0.1"
if [[ -n "$TENANT_DOMAIN" ]]; then
  export TENANT_BASE_URL="http://${TENANT_DOMAIN}:${PORT}"
  RULES="${RULES},MAP ${TENANT_DOMAIN} 127.0.0.1"
  echo "[run_visual_qa] Tenant host for portal QA: ${TENANT_DOMAIN}"
else
  export TENANT_BASE_URL=""
  echo "[run_visual_qa] No Postgres tenant domain — tenant portal tests will skip (SQLite/local)."
fi
export PLAYWRIGHT_HOST_RULES="$RULES"

# Run the visual-QA spec one viewport group at a time, cycling the dev server
# before each so every group hits a fresh process. The spec's test titles are
# prefixed with the viewport name ("desktop: …", "mobile: …"); the standalone
# "server is reachable" smoke test rides along with the first group.
OVERALL_RC=0
VISUAL_QA_VIEWPORTS=("desktop" "tablet-portrait" "tablet-landscape" "mobile")
for _vp_index in "${!VISUAL_QA_VIEWPORTS[@]}"; do
  _vp="${VISUAL_QA_VIEWPORTS[$_vp_index]}"
  if [[ "$_vp_index" -eq 0 ]]; then
    _grep="(server is reachable|${_vp}:)"
  else
    _grep="${_vp}:"
  fi
  echo "[run_visual_qa] === viewport group: ${_vp} (fresh server) ==="
  stop_server
  start_server || { OVERALL_RC=1; break; }
  if ! node node_modules/playwright/cli.js test tests/e2e/ux-visual-qa.spec.js --grep "$_grep" --reporter=line; then
    OVERALL_RC=1
  fi
done

# Marketing truth spec — fresh server, single viewport surface.
echo "[run_visual_qa] === marketing-visual-truth (fresh server) ==="
stop_server
if start_server; then
  export MARKETING_BASE_URL="http://${PUBLIC_HOST}:${PORT}"
  if ! node node_modules/playwright/cli.js test tests/e2e/marketing-visual-truth.spec.js --reporter=line; then
    OVERALL_RC=1
  fi
else
  OVERALL_RC=1
fi

exit "$OVERALL_RC"
