#!/usr/bin/env python3
"""
Remove file-backed Django test SQLite databases under .django_test_dbs/.
Use when migrations fail with "table already exists" or similar corrupt state.
Close other processes (IDE test runner, Django shell) that may hold locks.

Usage:
  python scripts/clean_django_test_dbs.py
  python scripts/clean_django_test_dbs.py --all   # also remove pre_deploy_gate.sqlite3

Exit 0 even if some files are locked (prints skip message).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_DB_DIR = REPO_ROOT / ".django_test_dbs"


def main() -> int:
    ap = argparse.ArgumentParser(description="Remove Django test SQLite files.")
    ap.add_argument(
        "--all",
        action="store_true",
        help="Remove every *.sqlite3 including pre_deploy_gate.sqlite3",
    )
    args = ap.parse_args()
    if not TEST_DB_DIR.is_dir():
        print(f"clean_django_test_dbs: {TEST_DB_DIR} not found; nothing to do.")
        return 0
    removed = 0
    for f in sorted(TEST_DB_DIR.glob("*.sqlite3")):
        if not args.all and f.name == "pre_deploy_gate.sqlite3":
            continue
        try:
            f.unlink()
            print(f"Removed {f.name}")
            removed += 1
        except OSError as e:
            print(f"Skip {f.name} (locked or in use): {e}", file=sys.stderr)
    if removed == 0 and not any(TEST_DB_DIR.glob("*.sqlite3")):
        print("clean_django_test_dbs: no sqlite files found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
