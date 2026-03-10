#!/usr/bin/env python3
"""
Fail if print( appears in apps/**/*.py outside tests/ or management/commands/.
Use in CI to enforce structured logging in application paths.
Exit 0 if none found; 1 and list files if found.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Allowlist: test and management command files may use print for dev/debug.
ALLOWLIST_DIRS = ("tests", "management", "migrations")
ROOT = Path(__file__).resolve().parent.parent
APPS = ROOT / "apps"

def main() -> int:
    found = []
    for py in APPS.rglob("*.py"):
        rel = py.relative_to(ROOT)
        parts = rel.parts
        if "apps" not in parts:
            continue
        # Allow tests, management commands, migrations
        if any(d in parts for d in ALLOWLIST_DIRS):
            continue
        try:
            lines = py.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                continue
            if re.search(r"\bprint\s*\(", line):
                found.append(f"{rel}:{i}")
                break
    if not found:
        print("OK: No print() in application code (apps/ excluding tests, management, migrations).")
        return 0
    print("ERROR: print() found in application code. Use logging.getLogger(__name__) instead.", file=sys.stderr)
    for f in sorted(found):
        print(f"  {f}", file=sys.stderr)
    return 1

if __name__ == "__main__":
    sys.exit(main())
