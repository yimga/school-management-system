"""Run scheduled tenant purges (auto-purge grace period elapsed)."""

from django.core.management.base import BaseCommand

from apps.schools.tenant_offboarding import run_scheduled_purges


class Command(BaseCommand):
    help = "Execute scheduled tenant purges (respects TENANT_AUTO_PURGE_ENABLED)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview purges without deleting",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=10,
            help="Max schools to process per run",
        )

    def handle(self, *args, **opts):
        result = run_scheduled_purges(
            actor=None,
            dry_run=bool(opts.get("dry_run")),
            limit=int(opts.get("limit") or 10),
        )
        if not result.get("ok"):
            self.stdout.write(self.style.WARNING(str(result)))
            return
        for entry in result.get("processed") or []:
            slug = entry.get("school_slug", "?")
            if entry.get("purged"):
                self.stdout.write(self.style.SUCCESS(f"Purged {slug}"))
            elif entry.get("skipped"):
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped {slug}: {entry.get('blockers')}"
                    )
                )
            else:
                self.stdout.write(f"Dry-run {slug}: {entry.get('row_total')} rows")
