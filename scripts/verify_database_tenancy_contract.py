#!/usr/bin/env python3
"""Phase P4 gate for tenant-safe database endpoint configuration."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    settings_text = (ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    checks = (ROOT / "apps" / "tenancy" / "checks.py").read_text(encoding="utf-8")
    rls_context = (ROOT / "apps" / "schools" / "rls_context.py").read_text(
        encoding="utf-8"
    )
    pooling_doc = (ROOT / "docs" / "PGBOUNCER_MULTI_SCHEMA.md").read_text(
        encoding="utf-8"
    )
    for token in (
        "DB_POOL_MODE",
        'if DB_POOL_MODE == "transaction"',
        "_DB_CONN_MAX_AGE = 0",
        "_DB_DISABLE_SS_CURSORS = True",
    ):
        if token not in settings_text:
            errors.append(f"database pool setting contract missing: {token}")
    for token in (
        "SUPPORTED_DB_POOL_MODES",
        "tenancy.E009",
        "app.current_school_id",
        "search_path",
    ):
        if token not in checks:
            errors.append(f"database pool startup guard missing: {token}")
    for token in (
        "quarantine_rls_connection",
        "connection.close()",
    ):
        if token not in rls_context:
            errors.append(f"RLS connection quarantine missing: {token}")
    for token in (
        "session-pooling or unpooled endpoint",
        "Do not use PgBouncer",
        "real PostgreSQL plus PgBouncer transaction",
    ):
        if token not in pooling_doc:
            errors.append(f"pooling SOT missing: {token}")

    commands = [
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.tenancy.tests.test_database_pooling_contract",
            "apps.schools.tests.test_rls_context",
            "apps.schools.tests.test_rls_context_reset_guards",
            "apps.schools.tests.test_rls_connection_quarantine",
            "apps.tenancy.tests.test_rls_boundary_contracts",
            "--verbosity=1",
        ],
        [sys.executable, "manage.py", "verify_database_pooling"],
        [sys.executable, "manage.py", "check"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            errors.append(f"verification command failed: {' '.join(command)}")

    if errors:
        print("DATABASE_TENANCY_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("DATABASE_TENANCY_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
