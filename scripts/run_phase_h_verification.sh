#!/usr/bin/env bash
# Phase H — Reliable verification subset (no DB required for core checks).
# RUNMYCAMPUS §11 Phase H: "Run full test suite and any smoke/E2E checks" — this script
# runs the Phase H slice that does not depend on a full migrated test DB.
# Exit 0 only if all steps pass. Use before deploy or when verifying Phase H automation.
#
# Usage: bash scripts/run_phase_h_verification.sh
# Optional: PHASE_H_SKIP_LIVE=1 to skip phase_h_audit --live (e.g. in minimal CI).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[phase_h_verification] Smoke URLs + Phase H URL reverse"
python manage.py test apps.accounts.tests.test_smoke_urls apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests --noinput -v 1

echo "[phase_h_verification] Phase H static audit"
python scripts/phase_h_audit.py

if [ "${PHASE_H_SKIP_LIVE:-0}" != "1" ]; then
  echo "[phase_h_verification] Phase H live URL reverse"
  python scripts/phase_h_audit.py --live
fi

echo "[phase_h_verification] Phase H reliable subset passed."
