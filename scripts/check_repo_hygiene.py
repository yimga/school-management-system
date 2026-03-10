#!/usr/bin/env python3
"""
Repo hygiene: fail CI on conflict markers, backup files, and debug debris.
Usage: python scripts/check_repo_hygiene.py [--exit-zero] [--base DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "htmlcov", ".pytest_cache", "media", "static", "backups", "staticfiles"}
# Only scan likely text files for conflict markers (skip binaries).
TEXT_EXTENSIONS = {".py", ".md", ".yml", ".yaml", ".json", ".sh", ".html", ".css", ".js", ".ts", ".sql", ".txt", ".toml", ".ini", ".cfg"}
BACKUP_GLOB = ("*.bak", "*.orig", "*.tmp")
# Full-line merge conflict markers (exact match per line)
CONFLICT_LINE_EXACT = ("<<<<<<<", "=======", ">>>>>>>")
# Or line starts with branch marker (<<<<<<< branch, >>>>>>> branch)
CONFLICT_LINE_STARTS = ("<<<<<<< ", ">>>>>>> ")


def main() -> int:
    ap = argparse.ArgumentParser(description="Check repo for conflict markers and backup/debug files.")
    ap.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    ap.add_argument("--base", default=".", help="Repo root (default: .)")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    if not base.is_dir():
        print(f"Not a directory: {base}", file=sys.stderr)
        return 2

    errors = []

    # Conflict markers in text files (only likely text extensions)
    for path in base.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_EXTENSIONS or path.name.startswith("."):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_bytes()
            if b"\x00" in text[:8192]:
                continue
            text_str = text[:50000].decode("utf-8", errors="replace")
            for line in text_str.splitlines():
                s = line.strip()
                if s in CONFLICT_LINE_EXACT:
                    errors.append(f"Conflict marker '{s}' in {path.relative_to(base)}")
                    break
                if any(line.startswith(prefix) for prefix in CONFLICT_LINE_STARTS):
                    errors.append(f"Conflict marker in {path.relative_to(base)}")
                    break
        except Exception:
            pass

    # Backup / debris files
    for pattern in BACKUP_GLOB:
        for path in base.rglob(pattern):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file():
                errors.append(f"Backup/debris file: {path.relative_to(base)}")

    if errors:
        print("Repo hygiene violations:\n", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 0 if args.exit_zero else 1
    print("check_repo_hygiene: No conflict markers or backup files found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
