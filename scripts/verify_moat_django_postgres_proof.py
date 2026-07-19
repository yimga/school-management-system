#!/usr/bin/env python3
"""Local Postgres moat Django proof (metric 16 companion; no GitHub required).

Mirrors the moat + query-count labels from django-tests-postgres.yml.
When DATABASE_URL is not PostgreSQL, exits 0 with an explicit skip
(same contract as verify_postgres_booking_ci_proof).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Keep in sync with .github/workflows/django-tests-postgres.yml moat labels.
MOAT_LABELS = (
    "apps.platform_runtime.tests.test_frontier_moat_runtime_proof",
    "apps.platform_runtime.tests.test_offline_multiday_replay_simulation",
    "apps.sync_engine.tests.test_crdt_live_rail_convergence",
    "apps.evals.tests.test_query_counts_rankings",
    "apps.academics.tests.test_query_counts_homework_gradebook",
    "apps.finance.tests.test_query_counts_family_billing",
    "apps.portal.tests.test_query_counts_teacher_completion",
    "apps.portal.tests.test_query_counts_attendance_rollcall",
)


def main() -> int:
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url.startswith("postgresql"):
        print(
            "verify_moat_django_postgres_proof: skip "
            "(DATABASE_URL is not PostgreSQL)",
            file=sys.stderr,
        )
        return 0

    cmd = [
        sys.executable,
        "manage.py",
        "test",
        *MOAT_LABELS,
        "--settings=config.settings",
        "--verbosity=1",
        "--no-input",
    ]
    env = os.environ.copy()
    env.setdefault("USE_DJANGO_TENANTS", "0")
    result = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if result.returncode != 0:
        print("MOAT_DJANGO_POSTGRES_PROOF_FAIL", file=sys.stderr)
        return result.returncode
    print("MOAT_DJANGO_POSTGRES_PROOF_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
