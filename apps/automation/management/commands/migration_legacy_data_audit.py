"""
Audit migration runs with failures or errors for operator review (Wave 5 legacy cleaner).
"""

from django.core.management.base import BaseCommand

from apps.automation.models import MigrationRun


class Command(BaseCommand):
    help = "List recent migration runs with FAILED status or error_count > 0 (dry-run audit)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=30,
            help="Max rows per category",
        )

    def handle(self, *args, **options):
        lim = max(1, min(options["limit"], 500))
        failed = list(
            MigrationRun.objects.filter(status=MigrationRun.Status.FAILED)
            .order_by("-started_at")[:lim]
        )
        errs = list(
            MigrationRun.objects.filter(error_count__gt=0)
            .exclude(status=MigrationRun.Status.FAILED)
            .order_by("-started_at")[:lim]
        )
        self.stdout.write(self.style.WARNING(f"FAILED runs (last {lim}):"))
        for r in failed:
            self.stdout.write(
                f"  id={r.id} school={r.school_id} type={r.migration_type} "
                f"errors={r.error_count} at={r.started_at}"
            )
        if not failed:
            self.stdout.write("  (none)")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("PARTIAL/SUCCESS with error_count>0:"))
        for r in errs:
            self.stdout.write(
                f"  id={r.id} school={r.school_id} type={r.migration_type} "
                f"status={r.status} errors={r.error_count}"
            )
        if not errs:
            self.stdout.write("  (none)")
        self.stdout.write("")
        self.stdout.write(
            "Next: inspect execution_summary / rollback_snapshot on MigrationRun; "
            "re-run wizard with cleaned CSV."
        )
