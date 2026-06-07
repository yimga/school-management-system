#!/usr/bin/env python3
"""
Wave 1 gate: every first-party seeded app declares a valid capability contract.

Usage: python scripts/verify_marketplace_app_capability_contract.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django  # noqa: E402

django.setup()

from apps.marketplace.capability_contract import (  # noqa: E402
    enrich_manifest_capability_bindings,
    validate_capability_bindings,
)
from apps.marketplace.management.commands.seed_marketplace_apps import (  # noqa: E402
    FIRST_PARTY_APPS,
)


def main() -> int:
    failures: list[str] = []
    for app_def in FIRST_PARTY_APPS:
        slug = app_def.get("slug") or ""
        manifest = enrich_manifest_capability_bindings(slug, app_def.get("manifest") or {})
        ok, errors = validate_capability_bindings(manifest)
        if not ok:
            failures.append(f"{slug}: " + "; ".join(errors))
        bindings = manifest.get("capability_bindings") or []
        if not bindings:
            failures.append(f"{slug}: capability_bindings empty after enrich")

    if failures:
        print("MARKETPLACE_APP_CAPABILITY_CONTRACT_FAIL", file=sys.stderr)
        for line in failures[:40]:
            print(f"  - {line}", file=sys.stderr)
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more", file=sys.stderr)
        return 1

    print(
        f"MARKETPLACE_APP_CAPABILITY_CONTRACT_PASS ({len(FIRST_PARTY_APPS)} apps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
