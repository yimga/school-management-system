#!/usr/bin/env python3
"""Fail if git tracks secret-prone env files. Portable twin of check_no_committed_env.sh.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FORBIDDEN = (
    ".env",
    ".env.local",
    ".env.development.local",
    ".env.test.local",
    ".env.production.local",
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure git does not track forbidden env files."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"check_no_committed_env: {exc}", file=sys.stderr)
        return 1

    r = subprocess.run(
        ["git", "ls-files", *FORBIDDEN],
        cwd=root,
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
    raise SystemExit(main(None))
