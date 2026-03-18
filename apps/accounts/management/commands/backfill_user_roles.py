"""Backfill user.roles from user.role using ROLE_TEMPLATES (run once after extending ROLE_TEMPLATES)."""

from django.db.models import Count
from django.core.management import BaseCommand

from apps.accounts.models import AccessRole, User
from apps.accounts.signals import ROLE_TEMPLATES


class Command(BaseCommand):
    help = "Set user.roles from user.role for users who have a role but no AccessRoles assigned."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be updated.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        updated = 0
        no_roles = User.objects.annotate(n=Count("roles")).filter(n=0).exclude(role="")
        for user in no_roles:
            role_codes = ROLE_TEMPLATES.get(user.role)
            if not role_codes:
                continue
            roles = AccessRole.objects.filter(code__in=role_codes)
            if not roles.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"User '{user.username}' (role={user.role}): no AccessRole found for {role_codes}; skip."
                    )
                )
                continue
            if dry_run:
                self.stdout.write(
                    self.style.NOTICE(
                        f"Would set {user.username} (role={user.role}) -> {list(roles.values_list('code', flat=True))}"
                    )
                )
            else:
                user.roles.set(roles)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Updated {user.username} (role={user.role}) -> {list(roles.values_list('code', flat=True))}"
                    )
                )
            updated += 1
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Backfill complete: {updated} user(s) {'would be ' if dry_run else ''}updated."
            )
        )
