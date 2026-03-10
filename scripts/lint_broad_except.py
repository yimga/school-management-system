#!/usr/bin/env python3
"""
Plan A4 / §15: Flag broad 'except Exception' / 'except BaseException' in sensitive paths.
Use specific exception types or platform_runtime exceptions where possible.
Usage: python scripts/lint_broad_except.py [--strict] [--exit-zero]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {"migrations", "__pycache__", "venv", ".venv", "node_modules", "tests"}
# Paths where broad except is allowed (shims, legacy compat, or documented).
ALLOWED_PREFIXES = (
    "apps/platform_runtime/runtime_resolver.py",  # Uses exception taxonomy in log
    "apps/siteconfig/management/",
    "apps/compliance/management_commands.py",
    "scripts/",
)

PATTERNS = [
    (re.compile(r"\bexcept\s+Exception\s*:"), "except Exception:"),
    (re.compile(r"\bexcept\s+BaseException\s*:"), "except BaseException:"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description="Flag broad except in app code.")
    ap.add_argument("--strict", action="store_true", help="Exit 1 if any hit (for CI).")
    ap.add_argument("--exit-zero", action="store_true", help="Always exit 0 (report only).")
    ap.add_argument("--base", default=".", help="Base directory (default: .)")
    args = ap.parse_args()
    base = Path(args.base).resolve()
    if not base.is_dir():
        print(f"Not a directory: {base}", file=sys.stderr)
        return 2

    apps_dir = base / "apps"
    if not apps_dir.is_dir():
        return 0

    hits: list[tuple[str, int, str]] = []
    for py in apps_dir.rglob("*.py"):
        if any(part in SKIP_DIRS for part in py.parts):
            continue
        path_str = str(py.relative_to(base)).replace("\\", "/")
        if path_str.startswith("apps/") and ("/test_" in path_str or "/tests/" in path_str):
            continue
        allowed = any(path_str.startswith(p) for p in ALLOWED_PREFIXES)
        if allowed:
            continue
        try:
            text = py.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for pat, label in PATTERNS:
                if pat.search(line):
                    hits.append((path_str, i, line.strip()[:80]))
                    break

    if not hits:
        print("lint_broad_except: No broad except Exception/BaseException in non-allowed app paths.")
        return 0
    print("lint_broad_except: Broad except in app code (plan A4 / §15); prefer specific exceptions:\n")
    for path, line_no, snippet in hits[:50]:  # Cap output
        print(f"  {path}:{line_no}  {snippet}")
    if len(hits) > 50:
        print(f"  ... and {len(hits) - 50} more.")
    print(f"\nTotal: {len(hits)} hit(s). Use --strict to fail CI.")
    return (1 if args.strict else 0) if not args.exit_zero else 0


if __name__ == "__main__":
    sys.exit(main())
