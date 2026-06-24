#!/usr/bin/env python3
"""Batch 1728 Wave A — every portal sidebar baseline url_name must reverse (demo-school paths)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()

    from apps.siteconfig import portal_sidebar_items as psi

    failures: list[str] = []
    checked = 0

    for role, specs in psi._BASELINE_BY_ROLE.items():
        for item_id, _label, url_name, _icon, _section in specs:
            checked += 1
            path = psi._baseline_reverse(url_name)
            if not path:
                failures.append(f"{role} {item_id} {url_name}: _baseline_reverse returned empty")

    for item_id, _label, url_name, _icon, _section, _perm in psi._BASELINE_ADMIN:
        checked += 1
        path = psi._baseline_reverse(url_name)
        if not path:
            failures.append(f"admin {item_id} {url_name}: _baseline_reverse returned empty")

    if failures:
        print("verify_tenant_sidebar_baseline_integrity: FAIL")
        for line in failures:
            print(f"- {line}")
        return 1

    print(
        f"verify_tenant_sidebar_baseline_integrity: TENANT_SIDEBAR_BASELINE_INTEGRITY_PASS "
        f"({checked} baseline items)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
