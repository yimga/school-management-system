#!/usr/bin/env python3
"""
Wave 4.2: Flag get_tenant_cache_prefix(None) in tenant apps.
Tenant-specific caches must not use None (public prefix); pass request or school_id.
Usage: python scripts/lint_tenant_cache_prefix.py [--base REPO_ROOT] [--exit-zero]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Tenant apps where cache keys should be tenant-scoped (no None).
TENANT_APP_PREFIXES = (
    "apps/portal",
    "apps/evals",
    "apps/finance",
    "apps/people",
    "apps/communication",
    "apps/accounts",
    "apps/reports",
    "apps/analytics",
    "apps/requests",
    "apps/compliance",
)

SKIP_DIRS = {"migrations", "__pycache__", ".git", "venv", ".venv", "node_modules"}
# Files where get_tenant_cache_prefix(None) is allowed (test fixtures only).
ALLOWED_PREFIX_NONE = ("apps/evals/tests/",)

PATTERN = re.compile(r"get_tenant_cache_prefix\s*\(\s*None\s*\)")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Lint: no get_tenant_cache_prefix(None) in tenant apps."
    )
    ap.add_argument("--base", type=str, default=".", help="Repo root.")
    ap.add_argument(
        "--exit-zero", action="store_true", help="Always exit 0 (report only)."
    )
    args = ap.parse_args()
    root = Path(args.base).resolve()
    apps_dir = root / "apps"
    if not apps_dir.is_dir():
        print("Apps dir not found.", file=sys.stderr)
        return 0 if args.exit_zero else 1

    hits = []
    for app_path in apps_dir.iterdir():
        if not app_path.is_dir():
            continue
        rel_prefix = f"apps/{app_path.name}"
        if rel_prefix not in [p for p in TENANT_APP_PREFIXES]:
            continue
        for py in app_path.rglob("*.py"):
            rel = str(py.relative_to(root)).replace("\\", "/")
            if any(s in rel for s in SKIP_DIRS):
                continue
            if any(rel.startswith(a) for a in ALLOWED_PREFIX_NONE):
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for m in PATTERN.finditer(text):
                line = text[: m.start()].count("\n") + 1
                hits.append((rel, line))

    if not hits:
        print(
            "lint_tenant_cache_prefix: No get_tenant_cache_prefix(None) in tenant apps."
        )
        return 0
    print(
        "lint_tenant_cache_prefix: get_tenant_cache_prefix(None) in tenant apps (use request or school_id):",
        file=sys.stderr,
    )
    for rel, line in hits:
        print(f"  {rel}:{line}", file=sys.stderr)
    return 0 if args.exit_zero else 1


if __name__ == "__main__":
    sys.exit(main())
