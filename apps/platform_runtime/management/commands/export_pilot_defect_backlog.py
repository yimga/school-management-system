"""Export PilotDefect rows to var/evidence/geos-99/pilot/<slug>/defect_backlog.json."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.pilot_defect_closure import export_defect_backlog_json
from apps.schools.founding_tenant_defaults import resolve_founding_tenant_slug


class Command(BaseCommand):
    help = "Export redacted pilot defect backlog JSON for GEOS evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            default="",
            help=(
                "Pilot school slug (source_school_slug filter). "
                "Defaults to DEFAULT_TENANT_SLUG or demo-school."
            ),
        )

    def handle(self, *args, **options):
        school = (options.get("school") or "").strip() or resolve_founding_tenant_slug()
        path = export_defect_backlog_json(school)
        self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))
