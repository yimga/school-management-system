"""Audit which connectors still use the category-fallback glyph vs. a real
slug-specific glyph in static/sprites/integrations.svg.

Usage:
    python manage.py check_brand_assets
    python manage.py check_brand_assets --json
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.integrations_marketplace.brand_assets import BRAND_ASSETS, report


class Command(BaseCommand):
    help = "Report which connectors still use the category-fallback glyph."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **opts):
        r = report()
        if opts["json"]:
            self.stdout.write(json.dumps(r, indent=2))
            return
        self.stdout.write(self.style.SUCCESS(
            f"Total connectors: {r['total_connectors']}"
        ))
        self.stdout.write(
            f"  ✓ Real glyph in sprite: {len(r['with_slug_glyph'])}"
        )
        self.stdout.write(
            f"  ⚠ Category fallback only: {len(r['category_fallback_only'])}"
        )
        if r["category_fallback_only"]:
            self.stdout.write("\n  Connectors using category fallback (sorted):")
            assets_by_slug = {a.slug: a for a in BRAND_ASSETS}
            for slug in r["category_fallback_only"]:
                a = assets_by_slug.get(slug)
                if a is None:
                    self.stdout.write(f"    - {slug}: no brand-asset entry yet")
                    continue
                self.stdout.write(
                    f"    - {slug}: {a.license_status}"
                    + (f" — {a.press_kit_url}" if a.press_kit_url else "")
                )
        self.stdout.write(
            f"\n  License status across registry: {r['license_status_counts']}"
        )
