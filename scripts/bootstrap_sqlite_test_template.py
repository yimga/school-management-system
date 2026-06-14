#!/usr/bin/env python3
"""Build a fully migrated SQLite test DB file without running any tests.

Used by ``run_50_app_test_shards.py --isolation app`` so each app can copy a
clean schema snapshot instead of paying a full migration per app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))


def _rm_sqlite(path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        f = Path(str(path) + suffix) if suffix else path
        try:
            if f.exists():
                f.unlink()
        except OSError:
            pass


def bootstrap_template(db_path: Path, *, verbosity: int = 1) -> bool:
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _rm_sqlite(db_path)

    os.environ["RMC_SQLITE_TEST_MEMORY"] = "1"
    os.environ["RMC_SQLITE_TEST_USE_MEMORY_NAME"] = "0"
    os.environ["DJANGO_TEST_DB_FILE"] = str(db_path)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    # Simulate ``manage.py test`` so RUNNING_TESTS + TEST.NAME wiring apply.
    sys.argv = ["bootstrap_sqlite_test_template.py", "test"]

    import django
    from django.test.utils import setup_databases, setup_test_environment

    django.setup()
    setup_test_environment()
    old_config = setup_databases(verbosity=verbosity, interactive=False, keepdb=False)
    # Intentionally skip teardown_databases — caller owns the file snapshot.

    if not db_path.is_file() or db_path.stat().st_size < 1024:
        _rm_sqlite(db_path)
        return False
    _ = old_config
    return True


def main() -> int:
    target = REPO / ".django_test_dbs" / "iso_app_template.sqlite3"
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        target = Path(sys.argv[1])
    ok = bootstrap_template(target)
    if ok:
        print(f"OK: template ready at {target} ({target.stat().st_size} bytes)")
        return 0
    print(f"FAIL: could not build template at {target}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
