#!/usr/bin/env python3
"""
Phase B execution verification (batches 1+ wiring).

- Batch 0: still owned by verify_phase_5_siteconfig.py (0162 + lints).
- Batch 1: brand_experience.PlatformGlobalBranding migration exists; when a
  SiteSettings row exists, singleton pk=1 must exist after migrations.
- Batches 4-13: platform_runtime.PlatformPhaseBDomainSnapshot; when SiteSettings
  exists, one row per PHASE_B_SNAPSHOT_DOMAINS after migrations + save sync.

Exit 0 = OK; non-zero = fix migrations or backfill.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MIGRATION_0002 = (
    ROOT / "apps" / "brand_experience" / "migrations" / "0002_platform_global_branding.py"
)
MIGRATION_0007 = (
    ROOT
    / "apps"
    / "platform_runtime"
    / "migrations"
    / "0007_platform_phase_b_domain_snapshots.py"
)


def main() -> int:
    errors: list[str] = []

    if not MIGRATION_0002.is_file():
        errors.append(
            f"Missing Phase B Batch 1 migration: {MIGRATION_0002.relative_to(ROOT)}"
        )
    if not MIGRATION_0007.is_file():
        errors.append(
            "Missing Phase B Batches 4-13 migration: "
            f"{MIGRATION_0007.relative_to(ROOT)}"
        )

    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django
    from django.conf import settings

    gate_file = (os.environ.get("DJANGO_TEST_DB_FILE") or "").strip()
    if gate_file and settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
        gpath = Path(gate_file)
        if not gpath.is_absolute():
            gpath = ROOT / gpath
        settings.DATABASES["default"]["NAME"] = str(gpath)

    django.setup()

    from django.apps import apps
    from django.db import connection

    try:
        model = apps.get_model("brand_experience", "PlatformGlobalBranding")
        table_name = model._meta.db_table
        tables = connection.introspection.table_names()
        if table_name not in tables:
            errors.append(
                f"Table {table_name} missing - run migrations (brand_experience.0002)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformGlobalBranding table: {exc}")

    try:
        snap_model = apps.get_model("platform_runtime", "PlatformPhaseBDomainSnapshot")
        snap_table = snap_model._meta.db_table
        tables = connection.introspection.table_names()
        if snap_table not in tables:
            errors.append(
                f"Table {snap_table} missing - run migrations "
                "(platform_runtime.0007_platform_phase_b_domain_snapshots)."
            )
    except Exception as exc:
        errors.append(f"Could not verify PlatformPhaseBDomainSnapshot table: {exc}")

    try:
        from apps.siteconfig.models import SiteSettings
        from apps.brand_experience.models import PlatformGlobalBranding
        from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot
        from apps.platform_runtime.phase_b_domain_snapshots import PHASE_B_SNAPSHOT_DOMAINS

        if SiteSettings.objects.exists():
            if not PlatformGlobalBranding.objects.filter(pk=1).exists():
                errors.append(
                    "SiteSettings row exists but PlatformGlobalBranding pk=1 missing - "
                    "run migrations (brand_experience.0002_platform_global_branding)."
                )
            missing_domains = [
                d
                for d in PHASE_B_SNAPSHOT_DOMAINS
                if not PlatformPhaseBDomainSnapshot.objects.filter(pk=d).exists()
            ]
            if missing_domains:
                errors.append(
                    "SiteSettings present but Phase B domain snapshots incomplete "
                    f"(missing: {', '.join(missing_domains)}). Save SiteSettings once or "
                    "re-run migration 0007 seed."
                )
    except Exception as exc:
        errors.append(f"ORM consistency check failed: {exc}")

    if errors:
        print("Phase B execution verification FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print(
        "Phase B execution verification OK (Batch 1 PlatformGlobalBranding + "
        "Batches 4-13 PlatformPhaseBDomainSnapshot when SiteSettings present)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
