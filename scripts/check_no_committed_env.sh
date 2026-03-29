#!/usr/bin/env bash
# Delegates to Python so CI / verify_phases_3_11_gates share one implementation.
set -euo pipefail
_REPO="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
python "$_REPO/scripts/check_no_committed_env.py"
