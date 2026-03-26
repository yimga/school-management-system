#!/usr/bin/env bash
set -euo pipefail

APP_BASE_URL="${APP_BASE_URL:-}"
COLLABORA_BASE_URL="${COLLABORA_BASE_URL:-}"
WOPI_OFFICE_DOC_ID="${WOPI_OFFICE_DOC_ID:-}"
APP_SESSION_COOKIE="${APP_SESSION_COOKIE:-}"

python scripts/verify_collabora_wopi_smoke.py   --app-base "$APP_BASE_URL"   --collabora-base "$COLLABORA_BASE_URL"   --office-doc-id "$WOPI_OFFICE_DOC_ID"   --session-cookie "$APP_SESSION_COOKIE"
