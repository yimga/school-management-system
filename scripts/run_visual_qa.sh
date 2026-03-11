#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PORT="${VISUAL_QA_PORT:-8010}"
PUBLIC_HOST="${VISUAL_QA_PUBLIC_HOST:-runmycampus.com}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/visual-qa}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"

export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"

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

python - <<'PY'
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
user.save()
PY

python - <<PY
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

nohup env \
  SECURE_SSL_REDIRECT=0 \
  DEBUG=1 \
  VISUAL_QA_USERNAME="$VISUAL_USERNAME" \
  VISUAL_QA_PASSWORD="$VISUAL_PASSWORD" \
  python manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
SERVER_PID="$!"

for _ in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "http://127.0.0.1:${PORT}/migrate/" || true)"
  if [[ "$code" == "200" ]]; then
    break
  fi
  sleep 2
done

if [[ "${code:-}" != "200" ]]; then
  echo "run_visual_qa: server failed to become ready on port ${PORT}." >&2
  tail -n 80 "$RUNSERVER_LOG" >&2 || true
  exit 1
fi

export TEST_USERNAME="$VISUAL_USERNAME"
export TEST_PASSWORD="$VISUAL_PASSWORD"
export BASE_URL="http://127.0.0.1:${PORT}"
export PUBLIC_BASE_URL="http://${PUBLIC_HOST}:${PORT}"
export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"

node node_modules/playwright/cli.js test tests/e2e/ux-visual-qa.spec.js --reporter=line
