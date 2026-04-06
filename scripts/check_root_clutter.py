#!/usr/bin/env python3
"""
Fail when tracked repo-root files exceed the approved operational allowlist.

Historical reports, generated artifacts, snapshots, and status ledgers must
live under docs/archive/, artifacts/, or other scoped folders instead of the
repo root.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_ALLOWLIST = "scripts/allowlists/tracked_root_allowlist.json"


def _load_allowlist(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed = payload.get("allowed", [])
    if not isinstance(allowed, list):
        raise ValueError("tracked_root_allowlist.json must contain an 'allowed' list")
    return {str(item) for item in allowed}


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check tracked repo-root files against an allowlist."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    parser.add_argument(
        "--allowlist",
        default=DEFAULT_ALLOWLIST,
        help="Allowlist JSON path relative to repo root",
    )
    parser.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        print(f"check_root_clutter: {exc}", file=sys.stderr)
        return 1
    allowlist = _load_allowlist((base / args.allowlist).resolve())
    violations: list[str] = []
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=base,
            check=True,
            capture_output=True,
            text=True,
        )
        tracked_files = [
            line.strip()
            for line in proc.stdout.splitlines()
            if line.strip() and "/" not in line and "\\" not in line
        ]
    except Exception:
        tracked_files = [path.name for path in base.iterdir() if path.is_file()]

    for name in sorted(tracked_files):
        if name not in allowlist:
            violations.append(name)

    if violations:
        print(
            "check_root_clutter: tracked repo-root files must be moved or removed:\n",
            file=sys.stderr,
        )
        for name in sorted(violations):
            print(f"  {name}", file=sys.stderr)
        return 0 if args.exit_zero else 1

    print("check_root_clutter: tracked repo-root files match the allowlist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
