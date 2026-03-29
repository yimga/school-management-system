#!/usr/bin/env python3
"""Fail if git tracks secret-prone env files. Portable twin of check_no_committed_env.sh."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    ".env",
    ".env.local",
    ".env.development.local",
    ".env.test.local",
    ".env.production.local",
)


def main() -> int:
    r = subprocess.run(
        ["git", "ls-files", *FORBIDDEN],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(
            "check_no_committed_env: git ls-files failed (not a git work tree?)",
            file=sys.stderr,
        )
        if r.stderr:
            print(r.stderr, file=sys.stderr)
        return 1
    tracked = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    if tracked:
        print(
            "ERROR: These env files must not be committed. Remove from the repo: git rm --cached <file>",
            file=sys.stderr,
        )
        for t in tracked:
            print(t, file=sys.stderr)
        return 1
    print("OK: No forbidden env files tracked in git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
