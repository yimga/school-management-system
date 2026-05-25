"""Backfill PlatformOperatorProfile for all active platform operators."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.platform_runtime.operator_identity import ensure_platform_operator_profile


class Command(BaseCommand):
    help = "Ensure every active staff/superuser has a PlatformOperatorProfile (IAM seeding)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts only; do not write.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        qs = User.objects.filter(is_active=True).filter(is_staff=True)
        created = 0
        updated = 0
        for user in qs.iterator():
            if options["dry_run"]:
                self.stdout.write(f"would sync profile for {user.username}")
                continue
            before = getattr(user, "platform_operator_profile", None)
            profile = ensure_platform_operator_profile(user)
            if before is None and profile is not None:
                created += 1
            else:
                updated += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"operator profiles: scanned={qs.count()} created~={created} synced~={updated}"
            )
        )
