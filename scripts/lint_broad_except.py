#!/usr/bin/env python3
"""
Flag broad except usage.

Supports:
- full scan report mode
- baseline-enforced allowlist mode for high-risk files
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {"migrations", "__pycache__", "venv", ".venv", "node_modules", "tests"}
ALLOWED_PREFIXES = (
    "apps/platform_runtime/runtime_resolver.py",
    "apps/siteconfig/management/",
    "apps/compliance/management_commands.py",
    "scripts/",
)
PATTERNS = (
    re.compile(r"\bexcept\s+Exception\b"),
    re.compile(r"\bexcept\s+BaseException\b"),
)


def _scan_counts(base: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for root_name in ("apps", "config"):
        root = base / root_name
        if not root.is_dir():
            continue
        for py_path in root.rglob("*.py"):
            if any(part in SKIP_DIRS for part in py_path.parts):
                continue
            rel = py_path.relative_to(base).as_posix()
            if rel.startswith("apps/") and ("/tests/" in rel or "/test_" in rel):
                continue
            if any(rel.startswith(prefix) for prefix in ALLOWED_PREFIXES):
                continue
            try:
                text = py_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            count = 0
            for line in text.splitlines():
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                if any(pattern.search(line) for pattern in PATTERNS):
                    count += 1
            if count:
                counts[rel] = count
    return counts


def _load_allowlist(path: str | None) -> dict[str, int]:
    if not path:
        return {}
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    allowed = payload.get("allowed_counts", {})
    if not isinstance(allowed, dict):
        raise ValueError("allowlist must contain an 'allowed_counts' object")
    return {str(key).replace("\\", "/"): int(value) for key, value in allowed.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Flag broad except usage.")
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 when violations are found."
    )
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0.")
    parser.add_argument(
        "--allowlist", help="JSON file of file -> allowed broad-except count."
    )
    parser.add_argument("--base", default=".", help="Repo base path.")
    args = parser.parse_args()

    base = Path(args.base).resolve()
    if not (base / "apps").is_dir():
        return 0

    counts = _scan_counts(base)
    allowlist = _load_allowlist(args.allowlist)

    if allowlist:
        violations: list[tuple[str, int, int]] = []
        for path, allowed_count in sorted(allowlist.items()):
            actual = counts.get(path, 0)
            if actual > allowed_count:
                violations.append((path, actual, allowed_count))
        if not violations:
            print("lint_broad_except: baseline respected for high-risk paths.")
            return 0
        print("lint_broad_except: broad except baseline exceeded:\n")
        for path, actual, allowed_count in violations:
            print(f"  {path}: {actual} > allowed {allowed_count}")
        return 0 if args.exit_zero else 1

    if not counts:
        print(
            "lint_broad_except: No broad except Exception/BaseException in non-allowed paths."
        )
        return 0

    items = sorted(counts.items())
    print("lint_broad_except: Broad except usage found:\n")
    for path, count in items[:50]:
        print(f"  {path}: {count}")
    if len(items) > 50:
        print(f"  ... and {len(items) - 50} more.")
    total = sum(count for _path, count in items)
    print(f"\nTotal: {total} hit(s) across {len(items)} file(s).")
    if args.exit_zero:
        return 0
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
