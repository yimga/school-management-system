"""
Run health check for all active app installations (updates last_health_at and health_status).
Can be run from cron or via Celery beat. Use status=ok unless an optional check fails.
Run: python manage.py marketplace_health_check
§2.4: Typed exception tuple for record_installation_health loop (no broad except).
"""

import logging
from django.core.management.base import BaseCommand

from apps.marketplace.models import AppInstallation
from apps.marketplace.services import record_installation_health
from apps.marketplace.tasks import _MARKETPLACE_HEALTH_CHECK_ERRORS
from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Update health status for all active app installations (last_health_at, health_status)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            type=str,
            default="ok",
            help="Status to set (default: ok). Use 'degraded' or 'error' if you have external checks.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report count, do not update.",
        )
        parser.add_argument(
            "--report-capability",
            action="store_true",
            help="Print capability-contract coverage for active MarketplaceApp rows.",
        )

    def handle(self, *args, **options):
        if options.get("report_capability"):
            self._report_capability_coverage()
            if options.get("dry_run") and not options.get("status"):
                return

        status = options["status"] or "ok"
        dry_run = options["dry_run"]
        qs = AppInstallation.objects.filter(
            status=AppInstallation.Status.ACTIVE,
            uninstalled_at__isnull=True,
        ).select_related("app", "school")
        count = qs.count()
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: would update {count} installations with status={status}."
                )
            )
            return
        updated = 0
        for inst in qs:
            try:
                record_installation_health(inst, status=status)
                updated += 1
            except _MARKETPLACE_HEALTH_CHECK_ERRORS as e:
                log_exception_with_context(
                    "marketplace_health_check command: record_installation_health failed",
                    school_id=getattr(inst, "school_id", None),
                    extra={"installation_id": inst.pk, "error": str(e)},
                )
        self.stdout.write(
            self.style.SUCCESS(
                f"Updated health for {updated} installations (status={status})."
            )
        )

    def _report_capability_coverage(self):
        from apps.marketplace.capability_contract import (
            enrich_manifest_capability_bindings,
            manifest_has_capability_contract,
        )
        from apps.marketplace.models import MarketplaceApp

        total = 0
        with_contract = 0
        for app in MarketplaceApp.objects.filter(is_active=True).only(
            "slug", "manifest"
        ):
            total += 1
            manifest = enrich_manifest_capability_bindings(app.slug, app.manifest or {})
            if manifest_has_capability_contract(manifest):
                with_contract += 1
        pct = round((with_contract / total) * 100, 1) if total else 0.0
        self.stdout.write(
            self.style.SUCCESS(
                f"Capability contract coverage: {with_contract}/{total} ({pct}%)"
            )
        )
