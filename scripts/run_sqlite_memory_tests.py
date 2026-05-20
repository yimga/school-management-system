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

Pass ``--fresh`` to migrate into a new timestamped DB file (avoids Windows file locks
on the stable cache). Omit ``--fresh`` to reuse ``rmc_sqlite_test_runner.sqlite3`` with
``--keepdb`` (added automatically).

Usage:
  python scripts/run_sqlite_memory_tests.py apps.analytics.tests --verbosity=1
  python scripts/run_sqlite_memory_tests.py apps.analytics.tests --verbosity=1 --keepdb
  python scripts/run_sqlite_memory_tests.py apps.siteconfig.tests.test_contrast_guard --fresh
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    tdir = root / ".django_test_dbs"
    tdir.mkdir(parents=True, exist_ok=True)

    argv = list(sys.argv[1:])
    fresh = "--fresh" in argv
    if fresh:
        # New timestamped TEST file + --keepdb avoids Windows hang on "Destroying old test database".
        argv = [a for a in argv if a != "--fresh"]
        if "--keepdb" not in argv:
            argv.append("--keepdb")

    # Stable path for --keepdb reuse; fresh runs use a new file so Windows never
    # blocks on "Destroying old test database" when another process holds the cache.
    # Callers may set DJANGO_TEST_DB_FILE to isolate a gate from the shared cache.
    stable = tdir / "rmc_sqlite_test_runner.sqlite3"
    if fresh:
        tfile = tdir / f"rmc_sqlite_test_runner_fresh_{int(time.time())}.sqlite3"
    else:
        explicit = (os.environ.get("DJANGO_TEST_DB_FILE") or "").strip()
        tfile = Path(explicit) if explicit else stable
        if not tfile.is_absolute():
            tfile = root / tfile
        if "--keepdb" not in argv:
            argv.append("--keepdb")

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
