#!/usr/bin/env python3
"""
Run Django tests with SQLite only (ignores DATABASE_URL).

Avoids:
- Hanging on Postgres when no server is available (DATABASE_URL=postgresql://...).
- Windows SQLite "Device busy" / stuck teardown when another process holds the default test DB file.

Uses a **stable file-backed** test database under ``.django_test_dbs/`` so ``--keepdb`` reuses
migrated schema across invocations (avoids 20+ minute cold migration on every run). Do **not** set
``RMC_SQLITE_TEST_USE_MEMORY_NAME=1`` here — that forces ``TEST NAME = :memory:`` and makes
``--keepdb`` ineffective (see ``config/settings.py``).

Pass ``--fresh`` to delete the cached test DB and migrate from scratch.

Usage:
  python scripts/run_sqlite_memory_tests.py apps.analytics.tests --verbosity=1
  python scripts/run_sqlite_memory_tests.py apps.analytics.tests --verbosity=1 --keepdb
  python scripts/run_sqlite_memory_tests.py apps.siteconfig.tests.test_contrast_guard --fresh
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    tdir = root / ".django_test_dbs"
    tdir.mkdir(parents=True, exist_ok=True)

    argv = list(sys.argv[1:])
    fresh = "--fresh" in argv
    if fresh:
        # Rebuild schema from scratch; --keepdb would reuse a corrupt partial DB.
        argv = [a for a in argv if a not in ("--fresh", "--keepdb")]

    # Stable path aligns with config/settings.py RMC_SQLITE_TEST_MEMORY runner + --keepdb reuse.
    tfile = tdir / "rmc_sqlite_test_runner.sqlite3"
    if fresh:
        for suffix in ("", "-journal", "-wal", "-shm"):
            candidate = Path(f"{tfile}{suffix}")
            if candidate.is_file():
                try:
                    candidate.unlink()
                except OSError:
                    pass

    env = os.environ.copy()
    env["RMC_SQLITE_TEST_MEMORY"] = "1"
    # File-backed TEST db so --keepdb persists across subprocess invocations.
    env["RMC_SQLITE_TEST_USE_MEMORY_NAME"] = "0"
    env["DJANGO_TEST_DB_FILE"] = str(tfile)
    env.setdefault("PYTHONUNBUFFERED", "1")
    cmd = [
        sys.executable,
        str(root / "manage.py"),
        "test",
        *argv,
        "--settings=config.settings",
        "--noinput",
    ]
    return subprocess.call(cmd, cwd=str(root), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
