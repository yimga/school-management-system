"""
Delete expired photo upload tokens to avoid DB and media bloat.
Tokens older than TOKEN_EXPIRY_HOURS (e.g. 48h) with no photo are removed.
Run periodically via cron or Celery beat.

Cron example (daily at 3 AM):
  0 3 * * * cd /path/to/project && python manage.py cleanup_photo_upload_tokens
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.portal.models import PhotoUploadToken

TOKEN_EXPIRY_HOURS = 48


class Command(BaseCommand):
    help = "Delete expired photo upload tokens (older than {} hours).".format(
        TOKEN_EXPIRY_HOURS
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report how many would be deleted.",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timezone.timedelta(hours=TOKEN_EXPIRY_HOURS)
        qs = PhotoUploadToken.objects.filter(created_at__lt=cutoff).filter(
            Q(photo="") | Q(photo__isnull=True)
        )
        count = qs.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS("No expired tokens to delete."))
            return
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    "Would delete {} expired token(s). Run without --dry-run to delete.".format(
                        count
                    )
                )
            )
            return
        qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                "Deleted {} expired photo upload token(s).".format(count)
            )
        )
