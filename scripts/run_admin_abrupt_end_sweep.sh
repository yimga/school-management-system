#!/usr/bin/env bash
# Admin-only abrupt-end sweep (P3): all admin_changelist routes from control_plane_sweep_routes.json.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8012}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
TENANT_HOST="${VISUAL_QA_TENANT_HOST:-demo-school.runmycampus.com}"
TENANT_SLUG="${TENANT_SWEEP_SLUG:-demo-school}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/admin-platform-proof}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"

mkdir -p "$ARTIFACT_DIR" artifacts

export SWEEP_TIER="${SWEEP_TIER:-admin_changelist}"
export DEBUG="${DEBUG:-1}"
export SWEEP_PATHS="${SWEEP_PATHS:-/admin/}"
export SWEEP_INCLUDE_TENANT="${SWEEP_INCLUDE_TENANT:-1}"
export SWEEP_SKIP_HEALTH="${SWEEP_SKIP_HEALTH:-0}"
export SWEEP_HEALTH_SECS="${SWEEP_HEALTH_SECS:-120}"
export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"
export VISUAL_QA_MANAGER_HOST="$MANAGER_HOST"
export VISUAL_QA_PORT="$PORT"
export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"
export VISUAL_QA_TENANT_HOST="$TENANT_HOST"
export TENANT_BASE_URL="http://${TENANT_HOST}:${PORT}"
export TENANT_E2E_BASE_URL="$TENANT_BASE_URL"
export TENANT_SWEEP_USERNAME="${TENANT_SWEEP_USERNAME:-demo.admin}"
export TENANT_SWEEP_PASSWORD="${TENANT_SWEEP_PASSWORD:-Test1234}"
export PLAYWRIGHT_HOST_RULES="MAP ${MANAGER_HOST} 127.0.0.1,MAP ${TENANT_HOST} 127.0.0.1"
export PLAYWRIGHT_TENANT_HOST_RULES="$PLAYWRIGHT_HOST_RULES"

"${PYTHON_CMD}" scripts/generate_control_plane_sweep_routes.py --write
"${PYTHON_CMD}" scripts/generate_tenant_admin_sweep_routes.py --write

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_admin_abrupt_end_sweep: run npm ci first." >&2
  exit 1
fi

seed_qa_user() {
  "${PYTHON_CMD}" - <<PY
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u, _ = User.objects.get_or_create(
    username="${VISUAL_USERNAME}",
    defaults={"is_staff": True, "is_superuser": True, "role": "SUPERADMIN"},
)
u.is_staff = True
u.is_superuser = True
u.role = "SUPERADMIN"
u.set_password("${VISUAL_PASSWORD}")
u.save()
print(f"Seeded manager QA user: {u.username}")
try:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    TOTPDevice.objects.filter(user=u).delete()
    device, _ = TOTPDevice.objects.update_or_create(
        user=u,
        name="e2e-playwright",
        defaults={"confirmed": True},
    )
    device.key = os.environ.get(
        "VISUAL_QA_TOTP_HEX_KEY",
        "eab95095c004f245721ba0fa7ebf82d5dc73",
    )
    device.save()
    print(f"Seeded TOTP device e2e-playwright for {u.username}")
except Exception as exc:
    print(f"WARN: TOTP seed skipped for {u.username}: {exc}")
PY
  "${PYTHON_CMD}" - <<PY
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from apps.schools.models import School

school, created = School.objects.get_or_create(
    slug="${TENANT_SLUG}",
    defaults={
        "name": "Admin proof tenant",
        "subdomain": "${TENANT_SLUG}",
        "country_code": "US",
        "timezone": "America/New_York",
        "is_active": True,
    },
)
dirty = []
if not school.is_active:
    school.is_active = True
    dirty.append("is_active")
if not school.subdomain:
    school.subdomain = "${TENANT_SLUG}"
    dirty.append("subdomain")
if dirty:
    school.save(update_fields=dirty)
print(f"{'Created' if created else 'Reused'} tenant proof school: {school.slug}")
PY
  "${PYTHON_CMD}" manage.py seed_demo_tenant_users --school-slug="${TENANT_SLUG}" --password="${TENANT_SWEEP_PASSWORD}"
  "${PYTHON_CMD}" - <<PY
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
from django_otp.plugins.otp_totp.models import TOTPDevice
user = get_user_model().objects.get(username="${TENANT_SWEEP_USERNAME}")
user.is_active = True
user.is_staff = True
user.is_superuser = True
user.save(update_fields=["is_active", "is_staff", "is_superuser"])
device, _ = TOTPDevice.objects.update_or_create(
    user=user,
    name="e2e-playwright",
    defaults={"confirmed": True},
)
device.key = os.environ.get(
    "VISUAL_QA_TOTP_HEX_KEY",
    "eab95095c004f245721ba0fa7ebf82d5dc73",
)
device.save()
print(f"Seeded tenant QA user and MFA: {user.username}")
PY
}

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${SWEEP_SKIP_HEALTH:-0}" == "1" ]] && curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
  seed_qa_user
else
  if ! curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
    "${PYTHON_CMD}" manage.py migrate --noinput
    seed_qa_user
    nohup env SECURE_SSL_REDIRECT=0 DEBUG=1 CSRF_COOKIE_SECURE=0 SESSION_COOKIE_SECURE=0 \
      CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${MANAGER_HOST}:${PORT},http://${TENANT_HOST}:${PORT}" \
      "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
    SERVER_PID="$!"
    code=""
    for _ in $(seq 1 60); do
      code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" -H 'Accept: application/json' "http://127.0.0.1:${PORT}/-/version/" || true)"
      [[ "$code" == "200" ]] && break
      sleep 2
    done
    if [[ "${code:-}" != "200" ]]; then
      echo "run_admin_abrupt_end_sweep: server not ready (HTTP ${code:-none})." >&2
      tail -n 40 "$RUNSERVER_LOG" >&2 || true
      exit 1
    fi
  else
    seed_qa_user
  fi
fi

if [[ -f scripts/seed_manager_playwright_auth.js ]]; then
  rm -f artifacts/manager-playwright-auth.json
  node scripts/seed_manager_playwright_auth.js
fi

node scripts/verify_platform_abrupt_end_sweep.mjs
