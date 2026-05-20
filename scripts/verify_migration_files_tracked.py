#!/usr/bin/env python3
"""Fail when Django migration files are gitignored or untracked.

Prevents Render deploy drift where ``*Conflict*.py`` in .gitignore silently
drops migration files from the release artifact.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _git_available(root: Path) -> bool:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and proc.stdout.strip() == "true"
    except OSError:
        return False


def main() -> int:
    import os

    root = Path(__file__).resolve().parent.parent
    artifact_only = "--artifact-only" in sys.argv or os.environ.get("RMC_RECOVERY_RUNTIME", "").strip() in {
        "1",
        "true",
        "yes",
    }
    migrations = sorted(
        p for p in root.glob("apps/*/migrations/*.py")
        if p.name != "__init__.py"
    )
    if not migrations:
        print("verify_migration_files_tracked: no migration files found", file=sys.stderr)
        return 1

    if artifact_only or not _git_available(root):
        print(
            f"verify_migration_files_tracked: PASS ({len(migrations)} migration files on disk; "
            "git tracking skipped — runtime/deploy artifact mode)"
        )
        return 0

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
