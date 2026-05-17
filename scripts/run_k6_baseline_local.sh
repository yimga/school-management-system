#!/usr/bin/env bash
# Run k6 baseline against local Django (batch 1236). Requires k6 on PATH.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
BASE_URL="${K6_BASE_URL:-http://127.0.0.1:8000}"
export K6_BASE_URL="$BASE_URL"
if ! command -v k6 >/dev/null 2>&1; then
  echo "k6 not installed — skip (install from https://k6.io/docs/get-started/installation/)"
  exit 0
fi
SUMMARY="${K6_SUMMARY_EXPORT:-artifacts/k6/summary.json}"
mkdir -p "$(dirname "$SUMMARY")"
echo "[k6] targeting $K6_BASE_URL"
k6 run --summary-export="$SUMMARY" tests/load/k6_baseline.js
python scripts/record_k6_baseline_results.py --summary "$SUMMARY" --base-url "$K6_BASE_URL"
