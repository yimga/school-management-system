#!/usr/bin/env python3
"""
Emit a unique SQLite path for Django tests (file-backed, no sharing across concurrent runs).

Usage:
  export DJANGO_TEST_DB_FILE=$(python scripts/generate_test_db_path.py)
  python manage.py test --noinput

Options:
  --dir PATH   Override directory (default: <repo>/.django_test_dbs)
  --basename NAME  Use fixed basename (still unique unless NAME contains {token})
"""
from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="Directory for the sqlite file (default: repo/.django_test_dbs)",
    )
    parser.add_argument(
        "--basename",
        default=None,
        help="Optional basename; {ts} and {uuid} are substituted",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    repo = here.parent
    db_dir = args.dir or (repo / ".django_test_dbs")
    db_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d_%H%M%S")
    token = uuid.uuid4().hex[:10]
    if args.basename:
        name = (
            args.basename.replace("{ts}", ts)
            .replace("{uuid}", token)
            .replace("{pid}", str(os.getpid()))
        )
        if "{ts}" not in args.basename and "{uuid}" not in args.basename and "{pid}" not in args.basename:
            stem = Path(args.basename).stem
            suffix = Path(args.basename).suffix or ".sqlite3"
            name = f"{stem}_{ts}_{token}{suffix}"
    else:
        name = f"test_{ts}_{token}.sqlite3"

    path = db_dir / name
    # Print for POSIX shells / PowerShell capture
    sys.stdout.write(str(path.resolve()))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
