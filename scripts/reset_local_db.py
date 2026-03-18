#!/usr/bin/env python3
"""
Remove the local SQLite DB file and run migrations to create a fresh one.
Use when you see: sqlite3.DatabaseError: database disk image is malformed

Run from project root (same folder as manage.py):
  python scripts/reset_local_db.py

Then create a superuser:
  python manage.py createsuperuser
"""

import os
import subprocess
import sys
from pathlib import Path


def main():
    base = Path(__file__).resolve().parent.parent
    db_file = base / "db_working.sqlite3"

    print("Project root:", base)
    print("DB file:     ", db_file)

    os.chdir(base)

    if db_file.exists():
        db_file.unlink()
        print("Removed (was corrupted or stale).")
    else:
        print("Not present (will be created).")

    os.environ["DB_FILE"] = "db_working.sqlite3"
    result = subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"],
        cwd=base,
        env=os.environ,
        timeout=300,
    )
    if result.returncode != 0:
        print("Migration failed.", file=sys.stderr)
        sys.exit(result.returncode)
    print("Done. Run: python manage.py createsuperuser")


if __name__ == "__main__":
    main()
