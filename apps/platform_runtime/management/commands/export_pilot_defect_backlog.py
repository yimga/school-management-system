"""Export PilotDefect rows to var/evidence/geos-99/pilot/<slug>/defect_backlog.json."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.platform_runtime.pilot_defect_closure import export_defect_backlog_json


class Command(BaseCommand):
    help = "Export redacted pilot defect backlog JSON for GEOS evidence."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            default="gilead-school",
            help="Pilot school slug (source_school_slug filter).",
        )

    def handle(self, *args, **options):
        school = (options.get("school") or "gilead-school").strip()
        path = export_defect_backlog_json(school)
        self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))
