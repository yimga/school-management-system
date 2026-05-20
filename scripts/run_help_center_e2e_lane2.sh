#!/usr/bin/env bash
# Lane 2 — Playwright help-center crawl (live Django required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export E2E_USERNAME="${E2E_USERNAME:-demo.admin}"
export E2E_PASSWORD="${E2E_PASSWORD:-Test1234}"
export E2E_MANAGER_USERNAME="${E2E_MANAGER_USERNAME:-admin}"
export E2E_MANAGER_PASSWORD="${E2E_MANAGER_PASSWORD:-Sch00l_1234}"
export BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
export E2E_TENANT_HOST="${E2E_TENANT_HOST:-gilead-school.runmycampus.com:8000}"

echo "Applying portal migrations (vector_embedding, etc.)..."
python manage.py migrate portal --noinput
python manage.py seed_demo_tenant_users --school-slug gilead-school || true

if ! curl -sf -o /dev/null "${BASE_URL}/"; then
  echo "Django is not reachable at ${BASE_URL}."
  echo "Start in another terminal: python manage.py runserver 127.0.0.1:8000"
  exit 1
fi

echo "Running Playwright help-center crawl..."
npm run test:e2e:help-center
