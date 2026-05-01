#!/usr/bin/env bash
# Delegates to scripts/run_sqlite_memory_tests.py (unique SQLite test DB + Postgres bypass).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python scripts/run_sqlite_memory_tests.py "$@"
