"""Release hygiene script (SOT batch 1208).

Removes development artifacts that must NOT ship in a release tarball:
  * __pycache__ directories
  * .pyc / .pyo / .pyd files
  * .django_test_dbs/ test SQLite DBs
  * tmp/screenshots/, var/tmp/, .tmp_test_artifacts/
  * gate_log*.txt, full_test_run.txt, test_output.txt
  * stray *.sqlite3 / *.sqlite3-journal at the repo root

It does NOT remove:
  * .env / .env.local (would discard secrets)
  * db.sqlite3 owned by an active dev session

Run with --dry-run to preview, or --apply to delete.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path


REMOVE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".django_test_dbs",
    ".tmp_test_artifacts",
    ".tmp_test_raw_sql_usage",
    "htmlcov",
}

REMOVE_DIR_PREFIXES = (
    "pytest-cache-files-",
)

REMOVE_FILE_NAMES = {
    "gate_log.txt",
    "gate_log2.txt",
    "full_test_run.txt",
    "test_output.txt",
    ".coverage",
}

REMOVE_FILE_SUFFIXES = (
    ".pyc",
    ".pyo",
    ".pyd",
    ".bak",
    ".tmp",
    ".sqlite3-journal",
    ".sqlite3.malformed",
    ".sqlite3.corrupted",
)

# Stray test SQLite DBs at repo root (default_*.sqlite3 etc.) — never db.sqlite3 itself.
ROOT_SQLITE_PATTERNS = (
    "default_",
    "db_buea_seed",
    "db_step",
    "db_fresh",
    "db_working",
)

PROTECTED = {".env", ".env.local", ".env.example"}


def _candidates(root: Path):
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Don't recurse into .git or node_modules
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", "venv", ".venv"}]

        for d in list(dirnames):
            if d in REMOVE_DIR_NAMES or any(d.startswith(p) for p in REMOVE_DIR_PREFIXES):
                yield ("dir", Path(dirpath) / d)
                dirnames.remove(d)

        for f in filenames:
            if f in PROTECTED:
                continue
            full = Path(dirpath) / f
            if f in REMOVE_FILE_NAMES:
                yield ("file", full)
                continue
            if any(f.endswith(suf) for suf in REMOVE_FILE_SUFFIXES):
                yield ("file", full)
                continue
            # Stray root-level test sqlite DBs only (not nested)
            if Path(dirpath) == root and f.endswith(".sqlite3") and any(
                f.startswith(prefix) for prefix in ROOT_SQLITE_PATTERNS
            ):
                yield ("file", full)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Delete (default is dry-run).")
    ap.add_argument("--root", default=".", help="Repo root (default cwd).")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    if not (root / "manage.py").exists():
        print(f"ERROR: {root} does not look like the Django project root", file=sys.stderr)
        return 2

    deleted = 0
    bytes_freed = 0
    for kind, path in _candidates(root):
        size = 0
        try:
            if kind == "dir":
                for p in path.rglob("*"):
                    try:
                        if p.is_file():
                            size += p.stat().st_size
                    except OSError:
                        pass
            else:
                size = path.stat().st_size
        except OSError:
            size = 0

        bytes_freed += size
        deleted += 1
        if args.apply:
            try:
                if kind == "dir":
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)
            except OSError as exc:
                print(f"WARN: could not remove {path}: {exc}", file=sys.stderr)
        print(f"{'DELETED' if args.apply else 'WOULD-DELETE'}: {kind:4s} {path}")

    mode = "applied" if args.apply else "dry-run"
    print(
        f"\nclean_release ({mode}): {deleted} candidates, "
        f"{bytes_freed/1024/1024:.1f} MB"
    )
    if not args.apply:
        print("Re-run with --apply to actually delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
