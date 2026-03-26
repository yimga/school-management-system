#!/usr/bin/env python3
"""
Apply migrations to the gate test DB file so --keepdb runs and verify_ux_completion see current schema.
Run from repo root with DJANGO_TEST_DB_FILE set (e.g. by pre_deploy_gate.sh).
Exits 0 on success; 1 on error; 2 if DJANGO_TEST_DB_FILE not set or not sqlite.

Recovery: If migrate fails with "table ... already exists" (half-applied DB) or the file is locked on
Windows, use a fresh path: DJANGO_TEST_DB_FILE=.django_test_dbs/pre_deploy_gate_run.sqlite3 — see docs/TEST_DATABASE.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Force use of the test DB file as the default DB for this process only
gate_file = (os.environ.get("DJANGO_TEST_DB_FILE") or "").strip()
if not gate_file:
    print("migrate_gate_test_db: DJANGO_TEST_DB_FILE not set; skipping.", file=sys.stderr)
    sys.exit(0)

path = Path(gate_file)
if not path.is_absolute():
    path = ROOT / path
path.parent.mkdir(parents=True, exist_ok=True)

import django
from django.conf import settings

if settings.DATABASES["default"]["ENGINE"] != "django.db.backends.sqlite3":
    print("migrate_gate_test_db: default DB is not sqlite; skipping.", file=sys.stderr)
    sys.exit(0)

# Point default DB at the gate test file so migrate runs against it
settings.DATABASES["default"]["NAME"] = str(path)
# Windows / parallel tools often hit transient "database is locked"; wait before failing.
settings.DATABASES["default"].setdefault("OPTIONS", {}).setdefault("timeout", 60)

django.setup()

# This script is not invoked via `manage.py test`, so settings would otherwise
# leave django.db at DEBUG when DEBUG=True — massive SQL spam and I/O slowdown.
import logging
import time

for _name in ("django.db.backends", "django.db.backends.schema"):
    logging.getLogger(_name).setLevel(logging.WARNING)

from django.core.management import call_command
from django.db import connection, connections
from django.db.utils import OperationalError

# Reduce Windows SQLite lock contention vs DELETE journal (default for Django test DB files).
connections.close_all()
try:
    connection.ensure_connection()
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
finally:
    connection.close()
    connections.close_all()

for attempt in range(8):
    connections.close_all()
    try:
        call_command("migrate", "--run-syncdb", verbosity=1)
        print("migrate_gate_test_db: gate test DB migrated.")
        sys.exit(0)
    except OperationalError as e:
        msg = str(e).lower()
        if "locked" in msg and attempt < 7:
            time.sleep(1.5 + float(attempt))
            continue
        print(f"migrate_gate_test_db: migrate failed: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"migrate_gate_test_db: migrate failed: {e}", file=sys.stderr)
        sys.exit(1)
