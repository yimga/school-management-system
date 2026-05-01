#!/usr/bin/env python3
"""
Run Django tests with SQLite only (ignores DATABASE_URL) and a unique file-backed test DB.

Avoids:
- Hanging on Postgres when no server is available (DATABASE_URL=postgresql://...).
- Windows SQLite "Device busy" when reusing the same test DB path while another process holds it.

Usage:
  python scripts/run_sqlite_memory_tests.py apps.analytics.tests --verbosity=1
  python scripts/run_sqlite_memory_tests.py apps.analytics.tests apps.reports.tests apps.platform_runtime.tests --verbosity=1 --keepdb
"""
from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    tdir = root / ".django_test_dbs"
    tdir.mkdir(parents=True, exist_ok=True)
    tfile = tdir / f"rmc_test_{uuid.uuid4().hex}.sqlite3"
    env = os.environ.copy()
    env["RMC_SQLITE_TEST_MEMORY"] = "1"
    env["DJANGO_TEST_DB_FILE"] = str(tfile)
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd = [
        sys.executable,
        str(root / "manage.py"),
        "test",
        *sys.argv[1:],
        "--settings=config.settings",
        "--noinput",
    ]
    return subprocess.call(cmd, cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
