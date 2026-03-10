#!/usr/bin/env python3
"""
Fail on unclassified csrf_exempt usage.
Usage: python scripts/lint_csrf_exempt_usage.py [--exit-zero] [--base DIR] [--allowlist FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__"}
PATTERN = re.compile(r"^\s*@csrf_exempt\b|method_decorator\(\s*csrf_exempt\b")


def _load_allowlist(path: Path) -> dict[str, dict[str, object]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("files", {})


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint csrf_exempt usage against an allowlist.")
    parser.add_argument("--base", default=".", help="Repo root (default: .)")
    parser.add_argument(
        "--allowlist",
        default="scripts/allowlists/csrf_exempt_allowlist.json",
        help="Allowlist JSON path",
    )
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    allowlist_path = (base / args.allowlist).resolve()
    allowlist = _load_allowlist(allowlist_path)
    counts: dict[str, int] = {}

    for root_name in ("apps", "config"):
        root = base / root_name
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(base).as_posix()
            text = path.read_text(encoding="utf-8", errors="replace")
            count = sum(1 for line in text.splitlines() if PATTERN.search(line))
            if count:
                counts[rel] = count

    violations: list[str] = []
    for rel, count in sorted(counts.items()):
        entry = allowlist.get(rel)
        if not entry:
            violations.append(f"Unexpected csrf_exempt usage in {rel} ({count} hit(s))")
            continue
        expected_count = int(entry.get("expected_count", 0))
        if count != expected_count:
            violations.append(
                f"csrf_exempt count changed in {rel}: expected {expected_count}, found {count}"
            )

    for rel in sorted(set(allowlist) - set(counts)):
        expected_count = int(allowlist[rel].get("expected_count", 0))
        if expected_count:
            violations.append(f"Allowlisted csrf_exempt path missing from scan: {rel}")

    if violations:
        print("lint_csrf_exempt_usage: violations detected:\n", file=sys.stderr)
        for msg in violations:
            print(f"  {msg}", file=sys.stderr)
        return 0 if args.exit_zero else 1

    print("lint_csrf_exempt_usage: All csrf_exempt usage is classified and unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
