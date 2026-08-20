#!/usr/bin/env bash
# Web entrypoint for self-hosted RunMyCampus. Applies migrations (django-tenants
# aware), then starts gunicorn via the project's resource-aware config. Lean by
# design — heavy first-run seeding (seed_render_users, platform catalogs, etc.)
# is operator-driven; see docs/SELF_HOST_MIGRATION.md and render_predeploy.sh.
set -euo pipefail
cd /app

echo "[selfhost] waiting for database..."
python - <<'PY'
import os, time, sys
import psycopg  # psycopg 3 — the driver in requirements.txt (psycopg[binary]>=3.1)
url = os.environ.get("DATABASE_URL", "")
for attempt in range(60):
    try:
        psycopg.connect(url).close()
        print("[selfhost] database is up")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - boot-time readiness poll
        time.sleep(2)
print("[selfhost] database not reachable after 120s", file=sys.stderr)
sys.exit(1)
PY

if [[ "${USE_DJANGO_TENANTS:-1}" == "1" ]]; then
  echo "[selfhost] migrate_schemas --shared"
  python manage.py migrate_schemas --shared --noinput
  python manage.py ensure_tenant_schemas || true
  echo "[selfhost] migrate_schemas --tenant"
  python manage.py migrate_schemas --tenant --noinput
else
  echo "[selfhost] migrate"
  python manage.py migrate --noinput
fi

# Surface edge-deployment footguns in the boot logs — the silent-dropped-mail
# console backend, the plain-HTTP-over-LAN secure-cookie login trap, wiped-on-
# redeploy local media, dead broker-less drainers, a placeholder SECRET_KEY.
# The readiness gate is otherwise a manual command an operator must know to run
# (docs/SELF_HOST_MIGRATION.md); running it every boot makes the box self-report.
# Advisory by default (never blocks boot); set RMC_EDGE_READINESS_STRICT=1 to make
# a FAIL-level finding abort startup (via `set -e`).
echo "[selfhost] edge readiness check"
if [[ "${RMC_EDGE_READINESS_STRICT:-0}" == "1" ]]; then
  python manage.py check_edge_readiness --strict
else
  python manage.py check_edge_readiness || true
fi

# Report the box<->cloud link in the boot logs. Deliberately NOT gated on
# RMC_EDGE_SYNC_ENABLED: a PAIRED box is an enabled box, and the state most worth
# printing is the one where the operator believes sync is on and it is not. Offline
# checks only (no --http) so boot never waits on the network. Advisory always.
echo "[selfhost] box <-> cloud link"
python manage.py verify_edge_link || true

# Edge auto-sync: one reconcile on boot so a power-loss / crash / abrupt-disconnect
# recovery pushes & pulls IMMEDIATELY, without waiting for the first scheduled
# interval. Backgrounded and swallowed — edge_autosync is offline-safe and self-gating
# (it no-ops unless this box is paired or RMC_EDGE_SYNC_ENABLED is set), so it must
# never delay or block boot.
#
# The shell condition was removed on purpose: it tested only the env var, so a box
# adopted through the pairing screen skipped its boot reconcile entirely. The command
# already makes this decision correctly, and it makes it the same way everything else
# does.
echo "[selfhost] edge auto-sync: initial reconcile on boot (backgrounded)"
( python manage.py edge_autosync >/dev/null 2>&1 || true ) &

echo "[selfhost] starting gunicorn"
exec gunicorn -c config/gunicorn.conf.py config.wsgi:application
