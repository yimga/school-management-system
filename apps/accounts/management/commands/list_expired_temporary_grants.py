"""List temporary role grants that have expired (optional: for notification or cleanup)."""

from django.core.management import BaseCommand
from django.utils import timezone

from apps.accounts.models import TemporaryRoleGrant


class Command(BaseCommand):
    help = "List temporary role grants that have expired (expires_at <= now)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count-only",
            action="store_true",
            help="Only print the count of expired grants.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        expired = TemporaryRoleGrant.objects.filter(expires_at__lte=now).order_by(
            "-expires_at"
        )
        count = expired.count()
        if options["count_only"]:
            self.stdout.write(str(count))
            return
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No expired temporary grants."))
            return
        self.stdout.write(self.style.WARNING(f"Expired temporary grants ({count}):"))
        for g in expired[:100]:
            self.stdout.write(
                f"  {g.user.username} <- {g.role.code} (expired {g.expires_at})"
            )
        if count > 100:
            self.stdout.write(f"  ... and {count - 100} more.")
