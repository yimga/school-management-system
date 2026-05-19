"""Seed deterministic analytics demo bundles (stdout JSON or optional file)."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.analytics.services.analytics_seeder_py import (
    seed_tenant_analytics_bundle,
    validate_bundle_integrity,
)


class Command(BaseCommand):
    help = "Emit TenantAnalyticsBundle JSON for a tenant slug (deterministic PRNG seeder)."

    def add_arguments(self, parser):
        parser.add_argument(
            "tenant_id",
            nargs="?",
            default="platform-overview",
            help="Tenant slug (e.g. platform-overview, marketing-demo)",
        )
        parser.add_argument(
            "--validate",
            action="store_true",
            help="Run integrity checks and exit non-zero on failure",
        )

    def handle(self, *args, **options):
        tenant_id = options["tenant_id"]
        bundle = seed_tenant_analytics_bundle(tenant_id)
        ok, errors = validate_bundle_integrity(bundle)
        if options["validate"] and not ok:
            self.stderr.write("; ".join(errors))
            raise SystemExit(1)
        self.stdout.write(json.dumps(bundle, indent=2))
        if ok:
            self.stdout.write(self.style.SUCCESS(f"SEED OK — {tenant_id}"))
        else:
            self.stderr.write(self.style.WARNING("; ".join(errors)))
