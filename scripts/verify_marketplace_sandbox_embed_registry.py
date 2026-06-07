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

from apps.marketplace.capability_contract import TOP_15_APP_SLUGS  # noqa: E402
from apps.marketplace.sandbox_embed_registry import (  # noqa: E402
    registry_validation_errors,
    widgets_dict_for_slug,
)


def main() -> int:
    errors = registry_validation_errors()
    for slug in sorted(TOP_15_APP_SLUGS):
        widgets = widgets_dict_for_slug(slug)
        if not widgets:
            errors.append(f"{slug}: widgets_dict_for_slug empty")
            continue
        primary = next(iter(widgets.values()), {})
        if not isinstance(primary, dict) or not primary.get("url_name"):
            errors.append(f"{slug}: primary widget missing url_name")

    if errors:
        print("MARKETPLACE_SANDBOX_EMBED_REGISTRY_FAIL", file=sys.stderr)
        for line in errors[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more", file=sys.stderr)
        return 1

    print(
        "MARKETPLACE_SANDBOX_EMBED_REGISTRY_PASS "
        f"({len(TOP_15_APP_SLUGS)} TOP_15 apps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
