#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
  elif [[ -x "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/Scripts/python.exe"
  else
    PYTHON_BIN="python"
  fi
fi

run_django_tests() {
  "${PYTHON_BIN}" manage.py test "$@" --keepdb --noinput -v 1
}

echo "[powerhouse_wave0] Django check"
"${PYTHON_BIN}" manage.py check

echo "[powerhouse_wave0] Migrations check"
"${PYTHON_BIN}" manage.py makemigrations --check --dry-run

echo "[powerhouse_wave0] Tenant model audit"
"${PYTHON_BIN}" manage.py audit_tenant_models --strict

echo "[powerhouse_wave0] RBAC and smoke targeted suite"
run_django_tests \
  apps.accounts.tests.test_smoke_urls \
  apps.siteconfig.tests.test_admin_ui_smoke \
  apps.api.tests.test_dashboard_api_rbac \
  apps.requests.tests.test_views_security \
  apps.accounts.tests.test_mfa_redirect_safety

WAVE0_DB_FILE_USER_SET=0
if [[ -n "${POWERHOUSE_WAVE0_DB_FILE:-}" ]]; then
  WAVE0_DB_FILE="${POWERHOUSE_WAVE0_DB_FILE}"
  WAVE0_DB_FILE_USER_SET=1
  mkdir -p "$(dirname "${WAVE0_DB_FILE}")"
  rm -f "${WAVE0_DB_FILE}"
else
  WAVE0_DB_FILE="$(mktemp "${TMPDIR:-/tmp}/gilead_wave0_gate.XXXXXX.sqlite3")"
fi

echo "[powerhouse_wave0] Bootstrap isolated DB for compliance checks"
DB_FILE="${WAVE0_DB_FILE}" "${PYTHON_BIN}" manage.py migrate --noinput

echo "[powerhouse_wave0] Seed compliance baseline"
DB_FILE="${WAVE0_DB_FILE}" "${PYTHON_BIN}" manage.py seed_compliance_baseline

echo "[powerhouse_wave0] Compliance auditor strict pass"
DB_FILE="${WAVE0_DB_FILE}" "${PYTHON_BIN}" manage.py compliance_auditor --strict --min-score 70

echo "[powerhouse_wave0] Access-control consistency scan"
set +e
ACCESS_OUTPUT="$(DB_FILE="${WAVE0_DB_FILE}" "${PYTHON_BIN}" manage.py verify_access_control)"
ACCESS_EXIT=$?
set -e
echo "${ACCESS_OUTPUT}"
if [[ ${ACCESS_EXIT} -ne 0 ]]; then
  echo "verify_access_control returned non-zero exit status: ${ACCESS_EXIT}" >&2
  exit ${ACCESS_EXIT}
fi
if echo "${ACCESS_OUTPUT}" | grep -Eq "Issues found: [1-9][0-9]*"; then
  echo "verify_access_control reported unresolved issues" >&2
  exit 1
fi

echo "[powerhouse_wave0] Render startup command sanity"
if ! grep -q "render_start_web.sh" render.yaml; then
  echo "render.yaml must reference scripts/release/render_start_web.sh" >&2
  exit 1
fi
if ! grep -q "render_start_web.sh" Procfile; then
  echo "Procfile must reference scripts/release/render_start_web.sh" >&2
  exit 1
fi

if [[ ${WAVE0_DB_FILE_USER_SET} -eq 0 ]]; then
  rm -f "${WAVE0_DB_FILE}" || true
fi

echo "[powerhouse_wave0] PASSED"
