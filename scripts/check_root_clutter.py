#!/usr/bin/env python3
"""
Fail when tracked repo-root files exceed the approved operational allowlist.

Historical reports, generated artifacts, snapshots, and status ledgers must
live under docs/archive/, artifacts/, or other scoped folders instead of the
repo root.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

DEFAULT_ALLOWLIST = "scripts/allowlists/tracked_root_allowlist.json"


def _load_allowlist(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    allowed = payload.get("allowed", [])
    if not isinstance(allowed, list):
        raise ValueError("tracked_root_allowlist.json must contain an 'allowed' list")
    return {str(item) for item in allowed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check tracked repo-root files against an allowlist.")
    parser.add_argument("--base", default=".", help="Repo root (default: .)")
    parser.add_argument(
        "--allowlist",
        default=DEFAULT_ALLOWLIST,
        help="Allowlist JSON path relative to repo root",
    )
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    args = parser.parse_args()

    base = Path(args.base).resolve()
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
        tracked_files = [line.strip() for line in proc.stdout.splitlines() if line.strip() and "/" not in line and "\\" not in line]
    except Exception:
        tracked_files = [path.name for path in base.iterdir() if path.is_file()]

    for name in sorted(tracked_files):
        if name not in allowlist:
            violations.append(name)

    if violations:
        print("check_root_clutter: tracked repo-root files must be moved or removed:\n", file=sys.stderr)
        for name in sorted(violations):
            print(f"  {name}", file=sys.stderr)
        return 0 if args.exit_zero else 1

    print("check_root_clutter: tracked repo-root files match the allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
