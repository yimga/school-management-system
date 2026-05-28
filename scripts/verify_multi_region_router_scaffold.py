#!/usr/bin/env python3
"""Batch 1535 — multi-region router scaffold (passes with ENABLE_MULTI_REGION off)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    import django

    django.setup()
    from django.conf import settings

    from apps.platform_runtime.dynamic_db_routing import resolve_school_db_alias
    from apps.platform_runtime.middleware_regional_db import RegionalDatabaseMiddleware

    findings: list[str] = []

    if not (ROOT / "apps/platform_runtime/dynamic_db_routing.py").is_file():
        findings.append("missing dynamic_db_routing.py")
    if not (ROOT / "apps/platform_runtime/middleware_regional_db.py").is_file():
        findings.append("missing middleware_regional_db.py")

    mw = "apps.platform_runtime.middleware_regional_db.RegionalDatabaseMiddleware"
    if mw not in getattr(settings, "MIDDLEWARE", []):
        findings.append("RegionalDatabaseMiddleware not in MIDDLEWARE")

    school = type(
        "S",
        (),
        {"dedicated_db_alias": "", "regional_cluster": "", "data_region": "EU"},
    )()
    if resolve_school_db_alias(school) is not None:
        findings.append("expected None when ENABLE_MULTI_REGION is off")

    if not callable(getattr(RegionalDatabaseMiddleware, "__call__", None)):
        findings.append("middleware not callable")

    if findings:
        print("verify_multi_region_router_scaffold: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_multi_region_router_scaffold: MULTI_REGION_ROUTER_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
