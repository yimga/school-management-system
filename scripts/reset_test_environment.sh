#!/usr/bin/env bash
# Hard reset local Django/pytest SQLite test artifacts and bytecode caches.
# Does NOT kill unrelated Python workloads unless they hold this repo's manage.py.
#
# Usage: bash scripts/reset_test_environment.sh [--kill-manage-py]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

KILL_MANAGE="${1:-}"

if [[ "${KILL_MANAGE}" == "--kill-manage-py" ]] || [[ "${RESET_KILL_MANAGE_PY:-}" == "1" ]]; then
  # Best-effort: only processes whose argv matches this repo + manage.py
  if command -v pkill >/dev/null 2>&1; then
    pkill -f "${ROOT}.*manage\\.py" 2>/dev/null || true
  fi
fi

if [[ -d "${ROOT}/.django_test_dbs" ]]; then
  rm -rf "${ROOT}/.django_test_dbs"/*
fi
mkdir -p "${ROOT}/.django_test_dbs"

# Bytecode caches (best-effort)
find "${ROOT}" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "${ROOT}" -type f -name '*.pyc' -delete 2>/dev/null || true

echo "reset_test_environment: OK (${ROOT})"
