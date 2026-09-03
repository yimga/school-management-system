#!/usr/bin/env bash
# Marketing axe ratchet — boot Django, sweep every marketing page with axe, and
# assert against var/a11y-marketing-axe-baseline.json.
#
# What it asserts (and deliberately does NOT assert): see the module docstring
# of scripts/run_marketing_axe_sweep.mjs. Short version — the failing PAGE COUNT
# and the set of failing (rule, foreground, background) COLOUR PAIRS are
# ratcheted; the raw violation node total is not, because reveal animations make
# it move on its own.
#
#   bash scripts/run_marketing_axe_ratchet.sh              # assert vs baseline
#   AXE_RATCHET_MODE=--report  bash scripts/…              # enumerate, exit 0
#   AXE_RATCHET_MODE=--write-baseline bash scripts/…       # re-cut the baseline
#
# Cost: ~3.5 min of browser time for 54 page-views on a warm machine, plus the
# Django boot. That is why this is a workflow and NOT part of
# scripts/pre_push_boundary_check.py — see the note in that file.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8010}"
PUBLIC_HOST="${VISUAL_QA_PUBLIC_HOST:-runmycampus.com}"
ARTIFACT_DIR="${AXE_RATCHET_ARTIFACT_DIR:-artifacts/a11y}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
MODE="${AXE_RATCHET_MODE:-}"

mkdir -p "$ARTIFACT_DIR"

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_marketing_axe_ratchet: run 'npm ci' first." >&2
  exit 1
fi

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "http://127.0.0.1:${PORT}/" || true)"
if [[ "$code" == "200" ]]; then
  echo "[axe-ratchet] Reusing server on port ${PORT}"
else
  nohup env SECURE_SSL_REDIRECT=0 DEBUG=1 \
    CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${PUBLIC_HOST}:${PORT}" \
    "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 45); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "http://127.0.0.1:${PORT}/" || true)"
    [[ "$code" == "200" ]] && break
    sleep 2
  done
  if [[ "${code:-}" != "200" ]]; then
    echo "run_marketing_axe_ratchet: server not ready (HTTP ${code:-none})." >&2
    tail -n 60 "$RUNSERVER_LOG" >&2 || true
    exit 1
  fi
fi

export MARKETING_BASE_URL="http://${PUBLIC_HOST}:${PORT}"
export PLAYWRIGHT_HOST_RULES="MAP ${PUBLIC_HOST} 127.0.0.1"

# No pipe here on purpose: piping into tee/tail would report the PIPE's exit
# code and a failing sweep would announce success.
if [[ -n "$MODE" ]]; then
  node scripts/run_marketing_axe_sweep.mjs "$MODE"
else
  node scripts/run_marketing_axe_sweep.mjs
fi
