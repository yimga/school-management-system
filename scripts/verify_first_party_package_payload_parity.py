#!/usr/bin/env python3
"""
Verify legacy seed_first_party_apps package IDs have non-empty PackageVersion payloads.

Usage: python scripts/verify_first_party_package_payload_parity.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from apps.packages.first_party_package_payloads import (  # noqa: E402
    FIRST_PARTY_APP_DEFINITIONS,
)
from apps.packages.models import PackageVersion  # noqa: E402


def main() -> int:
    failures: list[str] = []
    for item in FIRST_PARTY_APP_DEFINITIONS:
        package_id = str(item.get("package_id") or "").strip()
        version = str(item.get("version") or "1.0").strip()
        pv = (
            PackageVersion.objects.filter(package_id=package_id, version=version)
            .order_by("-created_at")
            .first()
        )
        if pv is None:
            failures.append(f"{package_id}: missing PackageVersion@{version}")
            continue
        sections = pv.payload_sections if isinstance(pv.payload_sections, dict) else {}
        if not sections:
            failures.append(f"{package_id}: empty payload_sections")
            continue
        primary = next(iter(sections.values()), None)
        if not isinstance(primary, dict) or not primary.get("package_id"):
            failures.append(f"{package_id}: payload missing package_id metadata")

    if failures:
        print("FIRST_PARTY_PACKAGE_PAYLOAD_PARITY_FAIL", file=sys.stderr)
        for line in failures[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(failures) > 30:
            print(f"  ... and {len(failures) - 30} more", file=sys.stderr)
        print("Run: python manage.py seed_first_party_apps", file=sys.stderr)
        return 1

    print(
        "FIRST_PARTY_PACKAGE_PAYLOAD_PARITY_PASS "
        f"({len(FIRST_PARTY_APP_DEFINITIONS)} legacy package IDs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
