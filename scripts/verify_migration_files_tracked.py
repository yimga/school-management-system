#!/usr/bin/env python3
"""Fail when Django migration files are gitignored or untracked.

Prevents Render deploy drift where ``*Conflict*.py`` in .gitignore silently
drops migration files from the release artifact.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    migrations = sorted(
        p for p in root.glob("apps/*/migrations/*.py")
        if p.name != "__init__.py"
    )
    if not migrations:
        print("verify_migration_files_tracked: no migration files found", file=sys.stderr)
        return 1

    ignored: list[str] = []
    untracked: list[str] = []

    for path in migrations:
        rel = path.relative_to(root).as_posix()
        proc = subprocess.run(
            ["git", "check-ignore", "-q", rel],
            cwd=root,
            capture_output=True,
        )
        if proc.returncode == 0:
            ignored.append(rel)
            continue
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=root,
            capture_output=True,
        )
        if proc.returncode != 0:
            untracked.append(rel)

    if not ignored and not untracked:
        print(
            f"verify_migration_files_tracked: PASS ({len(migrations)} migration files tracked)"
        )
        return 0

    print("verify_migration_files_tracked: FAIL", file=sys.stderr)
    if ignored:
        print("  gitignored migration files:", file=sys.stderr)
        for rel in ignored:
            print(f"    - {rel}", file=sys.stderr)
    if untracked:
        print("  untracked migration files (commit before deploy):", file=sys.stderr)
        for rel in untracked:
            print(f"    - {rel}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
