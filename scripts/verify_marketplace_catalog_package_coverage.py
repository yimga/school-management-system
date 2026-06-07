#!/usr/bin/env python3
"""
Verify all catalog slugs have legacy or catalog-native PackageVersion payloads.

Usage: python scripts/verify_marketplace_catalog_package_coverage.py
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

from apps.marketplace.catalog_package_coverage import (  # noqa: E402
    catalog_native_slugs,
    catalog_package_coverage_errors,
    legacy_mapped_slugs,
)
from apps.marketplace.management.commands.seed_marketplace_apps import (  # noqa: E402
    FIRST_PARTY_APPS,
)


def main() -> int:
    errors = catalog_package_coverage_errors()
    if errors:
        print("MARKETPLACE_CATALOG_PACKAGE_COVERAGE_FAIL", file=sys.stderr)
        for line in errors[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more", file=sys.stderr)
        print(
            "Run: python manage.py seed_marketplace_catalog_packages "
            "&& python manage.py seed_first_party_apps",
            file=sys.stderr,
        )
        return 1

    print(
        "MARKETPLACE_CATALOG_PACKAGE_COVERAGE_PASS "
        f"({len(FIRST_PARTY_APPS)} apps: "
        f"{len(legacy_mapped_slugs())} legacy + "
        f"{len(catalog_native_slugs())} catalog-native)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
