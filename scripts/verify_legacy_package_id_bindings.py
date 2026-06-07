#!/usr/bin/env python3
"""
Verify catalog slugs wire to legacy seed_first_party_apps package IDs where mapped.

Usage: python scripts/verify_legacy_package_id_bindings.py
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

from apps.marketplace.capability_contract import (  # noqa: E402
    enrich_manifest_capability_bindings,
    extract_capability_bindings,
)
from apps.marketplace.legacy_package_bindings import (  # noqa: E402
    CATALOG_SLUG_TO_LEGACY_PACKAGE_ID,
    LEGACY_PACKAGE_IDS,
    legacy_binding_validation_errors,
    resolve_legacy_package_id,
)


def main() -> int:
    errors = legacy_binding_validation_errors()
    for slug, legacy_id in sorted(CATALOG_SLUG_TO_LEGACY_PACKAGE_ID.items()):
        resolved = resolve_legacy_package_id(slug)
        if resolved != legacy_id:
            errors.append(f"{slug}: resolve mismatch {resolved!r} != {legacy_id!r}")
        manifest = enrich_manifest_capability_bindings(slug, {})
        if manifest.get("package_id") != legacy_id:
            errors.append(
                f"{slug}: manifest package_id {manifest.get('package_id')!r} != {legacy_id!r}"
            )
        bindings = extract_capability_bindings(manifest)
        pkg_targets = [
            b["target"]
            for b in bindings
            if b.get("kind") == "package_id"
        ]
        if legacy_id not in pkg_targets:
            errors.append(f"{slug}: package_id binding missing {legacy_id!r}")

    if errors:
        print("LEGACY_PACKAGE_ID_BINDINGS_FAIL", file=sys.stderr)
        for line in errors[:30]:
            print(f"  - {line}", file=sys.stderr)
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more", file=sys.stderr)
        print("Run: python manage.py seed_first_party_apps", file=sys.stderr)
        return 1

    print(
        "LEGACY_PACKAGE_ID_BINDINGS_PASS "
        f"({len(CATALOG_SLUG_TO_LEGACY_PACKAGE_ID)} catalog slugs -> "
        f"{len(LEGACY_PACKAGE_IDS)} legacy IDs)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
