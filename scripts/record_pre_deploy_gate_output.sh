#!/usr/bin/env bash
# Record pre_deploy_gate output for this release (RUNMYCAMPUS §12.1; BACKLOG §2f).
# Run from repo root. Writes docs/generated/pre_deploy_gate_run.txt.
# Required per RELEASE_CHECKLIST so gate results are recorded; nothing deferred.
# Optional: export SKIP_VISUAL_QA=1 (and DJANGO_TEST_DB_FILE if using gate sqlite) before invoking.
#
# To avoid re-running the full gate (~30–60+ min), copy an existing log instead:
#   cp /path/to/gate.log docs/generated/pre_deploy_gate_run.txt
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
mkdir -p docs/generated
if [[ -n "${RECORD_PRE_DEPLOY_GATE_FROM:-}" && -f "${RECORD_PRE_DEPLOY_GATE_FROM}" ]]; then
  cp "${RECORD_PRE_DEPLOY_GATE_FROM}" docs/generated/pre_deploy_gate_run.txt
  echo "[record_pre_deploy_gate_output] Copied ${RECORD_PRE_DEPLOY_GATE_FROM} → docs/generated/pre_deploy_gate_run.txt"
  exit 0
fi
bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt
echo "[record_pre_deploy_gate_output] Wrote docs/generated/pre_deploy_gate_run.txt"
