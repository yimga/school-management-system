#!/usr/bin/env python3
"""
Verify every marketplace catalog app slug has a PackageVersion with non-empty payload.

Usage: python scripts/verify_marketplace_package_payload_parity.py
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

from apps.marketplace.management.commands.seed_marketplace_apps import (  # noqa: E402
    FIRST_PARTY_APPS,
)
from apps.marketplace.marketplace_package_payloads import (  # noqa: E402
    resolve_package_id_for_app,
)
from apps.packages.models import PackageVersion  # noqa: E402


def main() -> int:
    failures: list[str] = []
    for app_def in FIRST_PARTY_APPS:
        slug = app_def.get("slug") or ""
        manifest = app_def.get("manifest") or {}
        version = str(app_def.get("version") or "1.0").strip()
        package_id = resolve_package_id_for_app(slug, manifest)
        pv = (
            PackageVersion.objects.filter(package_id=package_id, version=version)
            .order_by("-created_at")
            .first()
        )
        if pv is None:
            failures.append(f"{slug}: missing PackageVersion {package_id}@{version}")
            continue
        sections = pv.payload_sections if isinstance(pv.payload_sections, dict) else {}
        if not sections:
            failures.append(f"{slug}: empty payload_sections on {package_id}")
            continue
        primary = next(iter(sections.values()), None)
        if not isinstance(primary, dict) or not primary.get("app_slug"):
            failures.append(
                f"{slug}: payload missing app_slug metadata on {package_id}"
            )

    if failures:
        print("MARKETPLACE_PACKAGE_PAYLOAD_PARITY_FAIL", file=sys.stderr)
        for line in failures[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(failures) > 30:
            print(f"  ... and {len(failures) - 30} more", file=sys.stderr)
        print(
            "Run: python manage.py seed_marketplace_catalog_packages",
            file=sys.stderr,
        )
        return 1

    print(
        f"MARKETPLACE_PACKAGE_PAYLOAD_PARITY_PASS ({len(FIRST_PARTY_APPS)} catalog apps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
