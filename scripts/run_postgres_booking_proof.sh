#!/usr/bin/env bash
# Postgres proof for resource-booking ExclusionConstraint (Option A / metric 10).
# Mirrors .github/workflows/tenants-rls.yml — run after Docker Postgres is up.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${SECRET_KEY:=local-dev-only-not-for-production-64chars_____________________}"
: "${DATABASE_URL:=postgresql://postgres:postgres@127.0.0.1:5432/ci_tenants_rls}"
: "${USE_DJANGO_TENANTS:=0}"
export SECRET_KEY DATABASE_URL USE_DJANGO_TENANTS

echo "== migrate =="
python manage.py migrate --noinput

echo "== booking + RLS tests (Postgres) =="
python manage.py test \
  apps.schoolops.tests.test_resource_booking \
  --tag=tenants_rls \
  -v2 --no-input

echo "RESOURCE_BOOKING_POSTGRES_PROOF_PASS"
