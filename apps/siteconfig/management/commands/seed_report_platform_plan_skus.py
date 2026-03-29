"""
Upsert ``Plan`` rows aligned with ``billing_sku_registry.REPORT_PLATFORM_SKU_BUNDLES``.

Idempotent: ``update_or_create`` on slugs ``report-platform-standard`` and
``report-platform-advanced``. Does not alter BR-10 tier plans (``seed_br10_plan_skus``).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.siteconfig.billing_sku_registry import (
    REPORT_PLATFORM_SKU_ADVANCED,
    REPORT_PLATFORM_SKU_STANDARD,
    ordered_features_for_report_platform_bundle,
)
from apps.siteconfig.models_platform_catalog import Plan

_REPORT_PLAN_SPECS: tuple[tuple[str, str, str], ...] = (
    (
        REPORT_PLATFORM_SKU_STANDARD,
        "report-platform-standard",
        "Report platform (standard bundle)",
    ),
    (
        REPORT_PLATFORM_SKU_ADVANCED,
        "report-platform-advanced",
        "Report platform (advanced bundle)",
    ),
)


class Command(BaseCommand):
    help = (
        "Upsert Plan rows for report-platform SKU bundles (included_features from "
        "billing_sku_registry)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--bundle",
            action="append",
            dest="bundles",
            choices=[REPORT_PLATFORM_SKU_STANDARD, REPORT_PLATFORM_SKU_ADVANCED],
            help="Limit to one or more bundles (default: all). Repeatable.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print actions without writing the database.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        wanted = options.get("bundles") or None
        specs = _REPORT_PLAN_SPECS
        if wanted:
            wset = {str(x).strip().lower() for x in wanted}
            specs = tuple(s for s in specs if s[0] in wset)

        for bundle_key, slug, name in specs:
            features = ordered_features_for_report_platform_bundle(bundle_key)
            if dry_run:
                self.stdout.write(
                    f"[dry-run] {slug}: {name} -> included_features={features!r}"
                )
                continue
            _obj, created = Plan.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "included_features": features,
                    "is_active": True,
                },
            )
            verb = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(
                    f"{verb} Plan slug={slug!r} ({len(features)} features)"
                )
            )
