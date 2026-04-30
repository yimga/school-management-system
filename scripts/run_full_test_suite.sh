#!/usr/bin/env bash
# One-command stable full suite: reset caches, unique DB path, serial runner, stall guard.
#
# Env:
#   RMC_TEST_STALL_SECONDS   — idle kill threshold (default 300)
#   RMC_TEST_MAX_SECONDS     — wall clock cap (default 0 = none; e.g. 7200)
#   RESET_KILL_MANAGE_PY=1   — before reset, kill manage.py processes for this repo
#   SKIP_RESET=1             — skip reset_test_environment.sh (not recommended)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${SKIP_RESET:-0}" != "1" ]]; then
  if [[ "${RESET_KILL_MANAGE_PY:-0}" == "1" ]]; then
    bash "${ROOT}/scripts/reset_test_environment.sh" --kill-manage-py
  else
    bash "${ROOT}/scripts/reset_test_environment.sh"
  fi
fi

export RMC_RELIABLE_TEST_RUNNER="${RMC_RELIABLE_TEST_RUNNER:-1}"
export DJANGO_TEST_DB_FILE="$(python "${ROOT}/scripts/generate_test_db_path.py")"
export PYTHONUNBUFFERED="${PYTHONUNBUFFERED:-1}"

echo "run_full_test_suite: DJANGO_TEST_DB_FILE=${DJANGO_TEST_DB_FILE}"
echo "run_full_test_suite: starting manage.py test (serial, guarded)..."

STALL="${RMC_TEST_STALL_SECONDS:-300}"
MAX="${RMC_TEST_MAX_SECONDS:-0}"

if [[ "${MAX}" != "0" ]] && [[ -n "${MAX}" ]]; then
  exec python "${ROOT}/scripts/run_tests_with_guard.py" \
    --stall-seconds "${STALL}" \
    --max-seconds "${MAX}" \
    -- python manage.py test --noinput "$@"
else
  exec python "${ROOT}/scripts/run_tests_with_guard.py" \
    --stall-seconds "${STALL}" \
    --max-seconds 0 \
    -- python manage.py test --noinput "$@"
fi
