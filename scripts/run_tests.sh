#!/usr/bin/env bash
# Wave 9 Agent P (v3.58.x) — Linux / macOS / WSL test runner that
# matches the in-memory SQLite path used by scripts/run_tests_windows.ps1.
# Operators on *nix who want fast, isolated, single-process test runs
# (no shared file-backed cache to invalidate) use this. CI on Linux can
# alternatively run against Postgres — see .github/workflows/test-suite.yml.
#
# Usage:
#   ./scripts/run_tests.sh                                  # full pytest suite
#   ./scripts/run_tests.sh apps/schoolops/                  # one app
#   ./scripts/run_tests.sh apps/siteconfig/tests/test_cockpit_platform_pulse_service.py -x
#
# No interactive prompts — safe inside non-interactive tool runners.

set -euo pipefail

# Resolve repo root (this script lives in <root>/scripts/).
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
REPO_ROOT="$(dirname -- "$SCRIPT_DIR")"
cd "$REPO_ROOT"

echo "[run_tests] repo root: $REPO_ROOT"

# --- Env flags: route to in-memory SQLite test settings -----------------
export DJANGO_SETTINGS_MODULE="config.settings_test"
export RMC_SQLITE_TEST_MEMORY="1"
export RMC_SQLITE_TEST_USE_MEMORY_NAME="1"
export RMC_RUNNING_TESTS="1"
export PYTHONUNBUFFERED="1"
export DJANGO_LOG_LEVEL="CRITICAL"

echo "[run_tests] DJANGO_SETTINGS_MODULE=$DJANGO_SETTINGS_MODULE"
echo "[run_tests] in-memory SQLite: RMC_SQLITE_TEST_USE_MEMORY_NAME=$RMC_SQLITE_TEST_USE_MEMORY_NAME"

# --- Best-effort: clean stale SQLite journal/wal/shm files --------------
TEST_DB_DIR="$REPO_ROOT/.django_test_dbs"
if [ -d "$TEST_DB_DIR" ]; then
    # shellcheck disable=SC2010 — find -delete would race with locked files; we want to skip those.
    for f in "$TEST_DB_DIR"/*.sqlite3-journal "$TEST_DB_DIR"/*.sqlite3-wal "$TEST_DB_DIR"/*.sqlite3-shm; do
        if [ -e "$f" ]; then
            if rm -f "$f" 2>/dev/null; then
                echo "[run_tests] removed stale: $(basename "$f")"
            else
                echo "[run_tests] skip locked: $(basename "$f")"
            fi
        fi
    done
fi

# --- Invoke pytest ------------------------------------------------------
echo "[run_tests] invoking: python -m pytest $*"
exec python -m pytest "$@"
