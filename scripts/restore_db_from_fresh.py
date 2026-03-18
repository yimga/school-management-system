#!/usr/bin/env python3
"""
Restore db.sqlite3 from the fresh migrated DB (db_fresh.sqlite3).

Option A (no need to stop server): use the fresh DB via env var, then later swap when server is stopped:
  set DB_FILE=db_fresh.sqlite3
  python manage.py runserver
  (Windows CMD)
  export DB_FILE=db_fresh.sqlite3 && python manage.py runserver
  (Git Bash / bash)

Option B: stop the dev server (Ctrl+C), run this script, then start the server again:
  python scripts/restore_db_from_fresh.py
  python manage.py runserver
"""

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRESH = ROOT / "db_fresh.sqlite3"
DB = ROOT / "db.sqlite3"
CORRUPTED = ROOT / "db.sqlite3.corrupted"


def main():
    if not FRESH.exists():
        print(
            "db_fresh.sqlite3 not found. Run migrations with config.settings_freshdb first.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        if DB.exists():
            shutil.move(str(DB), str(CORRUPTED))
            print("Moved existing db.sqlite3 to db.sqlite3.corrupted")
        shutil.copy2(str(FRESH), str(DB))
        print("Copied db_fresh.sqlite3 -> db.sqlite3")
        print("You can now run: python manage.py runserver")
    except OSError as e:
        if "Device or resource busy" in str(e) or "Permission denied" in str(e):
            print(
                "Stop the dev server (Ctrl+C in the terminal running runserver), then run this script again.",
                file=sys.stderr,
            )
        else:
            print(e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
