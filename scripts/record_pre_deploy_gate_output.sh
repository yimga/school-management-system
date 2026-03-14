#!/usr/bin/env bash
# Record pre_deploy_gate output for this release (RUNMYCAMPUS §12.1; BACKLOG §2f).
# Run from repo root. Writes docs/generated/pre_deploy_gate_run.txt.
# Required per RELEASE_CHECKLIST so gate results are recorded; nothing deferred.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
mkdir -p docs/generated
bash scripts/pre_deploy_gate.sh 2>&1 | tee docs/generated/pre_deploy_gate_run.txt
echo "[record_pre_deploy_gate_output] Wrote docs/generated/pre_deploy_gate_run.txt"
