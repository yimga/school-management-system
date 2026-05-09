#!/bin/bash
# Post-deploy smoke test.
#
# Confirms the new deployment is alive and serves the parity contract:
#   - /-/version/  returns JSON containing commit_sha
#   - /health/     returns 2xx
#   - /-/version/  expected commit_sha matches RENDER_GIT_COMMIT (when set)
#
# Exit non-zero on failure so the deploy pipeline rolls back / pages.
#
# Usage:
#   BASE_URL=https://manager.runmycampus.com bash scripts/post_deploy_smoke.sh
#
# Optional:
#   EXPECTED_SHA=<7-64 hex>   to assert deployed SHA matches
set -eu

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
EXPECTED_SHA="${EXPECTED_SHA:-}"
TIMEOUT="${TIMEOUT:-15}"

echo "post_deploy_smoke: BASE_URL=${BASE_URL}"

# 1. /-/version/ must return JSON
version_body="$(curl --max-time "${TIMEOUT}" -fsSL -H 'Accept: application/json' "${BASE_URL}/-/version/" || true)"
if [ -z "${version_body}" ]; then
  echo "FAIL: /-/version/ returned empty body or non-2xx"
  exit 1
fi

echo "${version_body}" | python -c "import json,sys; d=json.loads(sys.stdin.read()); assert 'commit_sha' in d, 'no commit_sha key'; print('  /-/version/ ok commit_sha='+str(d.get('commit_sha')))"

# 2. /health/ must return 2xx
health_status="$(curl --max-time "${TIMEOUT}" -s -o /dev/null -w '%{http_code}' "${BASE_URL}/health/" || echo 000)"
if [ "${health_status}" -lt 200 ] || [ "${health_status}" -ge 300 ]; then
  echo "FAIL: /health/ returned HTTP ${health_status}"
  exit 1
fi
echo "  /health/ ok status=${health_status}"

# 3. Optional SHA assertion
if [ -n "${EXPECTED_SHA}" ]; then
  reported_sha="$(echo "${version_body}" | python -c "import json,sys; print(json.loads(sys.stdin.read()).get('commit_sha') or '')")"
  if [ -z "${reported_sha}" ]; then
    echo "FAIL: deployed /-/version/ did not report commit_sha"
    exit 1
  fi
  case "${reported_sha}" in
    "${EXPECTED_SHA}"*) echo "  SHA match: ${reported_sha:0:12} startswith ${EXPECTED_SHA:0:12}";;
    *) echo "FAIL: deployed SHA ${reported_sha} != expected ${EXPECTED_SHA}"; exit 1;;
  esac
fi

echo "post_deploy_smoke: PASS"
