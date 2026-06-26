#!/usr/bin/env python3
"""Postgres booking exclusion proof gate (metric 10 / CI companion).

Runs the DB-level overlap test class on PostgreSQL only; exits 0 with
``POSTGRES_BOOKING_EXCLUSION_PROOF_PASS`` when green. Safe to call from
``django-tests-postgres.yml`` after migrate.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        print(
            "verify_postgres_booking_ci_proof: skip (DATABASE_URL is not PostgreSQL)",
            file=sys.stderr,
        )
        return 0

    cmd = [
        sys.executable,
        "manage.py",
        "test",
        "apps.schoolops.tests.test_resource_booking.ResourceBookingPostgresExclusionTests",
        "apps.schoolops.tests.test_resource_booking.ResourceBookingServiceTests",
        "--tag=tenants_rls",
        "--settings=config.settings",
        "--verbosity=2",
        "--no-input",
    ]
    env = os.environ.copy()
    env.setdefault("USE_DJANGO_TENANTS", "0")
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if result.returncode != 0:
        print("POSTGRES_BOOKING_EXCLUSION_PROOF_FAIL", file=sys.stderr)
        return result.returncode
    print("POSTGRES_BOOKING_EXCLUSION_PROOF_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
