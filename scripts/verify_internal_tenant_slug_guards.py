#!/usr/bin/env python3
"""
AWS pillar: internal APIs that accept ?tenant= must call user_may_access_school_api
or resolve_school_from_request_param (mechanical regression guard).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (relative path, must contain one of these needles when file uses GET tenant param)
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "apps/api/analytics_viz_api.py",
        ("user_may_access_school_api", "_resolve_school_for_viz"),
    ),
    (
        "apps/api/config_diff_views.py",
        ("user_may_access_school_api",),
    ),
    (
        "apps/api/north_star_api_views.py",
        ("resolve_school_from_request_param",),
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    failures: list[str] = []
    for rel, needles in _RULES:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing file: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if 'GET.get("tenant")' in text or "GET.get('tenant')" in text:
            if not any(n in text for n in needles):
                failures.append(f"{rel}: tenant param without membership guard")
    if failures:
        for line in failures:
            print(line, file=sys.stderr)
        print(f"verify_internal_tenant_slug_guards: {len(failures)} FAIL", file=sys.stderr)
        return 1
    print("verify_internal_tenant_slug_guards: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
