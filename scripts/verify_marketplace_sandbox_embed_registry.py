#!/usr/bin/env python3
"""
Verify TOP_15 marketplace apps have sandbox embed registry entries with reversible URLs.

Usage: python scripts/verify_marketplace_sandbox_embed_registry.py
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
from apps.marketplace.sandbox_embed_registry import registry_validation_errors  # noqa: E402


def main() -> int:
    catalog_slugs = [app["slug"] for app in FIRST_PARTY_APPS]
    errors = registry_validation_errors(catalog_slugs=catalog_slugs)

    if errors:
        print("MARKETPLACE_SANDBOX_EMBED_REGISTRY_FAIL", file=sys.stderr)
        for line in errors[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more", file=sys.stderr)
        return 1

    print(
        "MARKETPLACE_SANDBOX_EMBED_REGISTRY_PASS "
        f"({len(catalog_slugs)} catalog apps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
