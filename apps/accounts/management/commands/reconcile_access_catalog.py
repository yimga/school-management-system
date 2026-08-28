"""Repair the live RBAC seed catalog from the authoritative data migrations.

Data migrations are normally one-shot.  A restored/partially-seeded database can
therefore have every migration marked applied while its ``Permission`` and
global ``AccessRole`` rows are incomplete.  These migration repair functions
are deliberately idempotent; replaying them restores missing catalog rows and
then reconciles SUPERADMIN and existing user role bindings.
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


REPAIR_MIGRATIONS = (
    "apps.accounts.migrations.0030_resync_accessrole_permissions",
    "apps.accounts.migrations.0048_rbac_completion_codes",
    "apps.accounts.migrations.0049_analytics_manage_code",
    "apps.accounts.migrations.0050_athletics_rbac_codes",
    "apps.accounts.migrations.0057_identity_reset_credentials_permission",
    "apps.accounts.migrations.0058_superadmin_full_permission_coverage",
    "apps.accounts.migrations.0059_discipline_refer_and_finance_view_invoice",
    "apps.accounts.migrations.0063_school_events_permission_codes",
)


class Command(BaseCommand):
    help = "Idempotently restore the Permission and global AccessRole catalogs."

    @transaction.atomic
    def handle(self, *args, **options):
        for module_name in REPAIR_MIGRATIONS:
            migration = import_module(module_name)
            migration.forwards(apps, None)

        call_command("sync_superadmin_permissions", verbosity=0)
        call_command("backfill_user_roles", verbosity=0)

        from apps.accounts.models import AccessRole, Permission

        role_count = AccessRole.objects.filter(school__isnull=True).count()
        permission_count = Permission.objects.count()
        self.stdout.write(
            self.style.SUCCESS(
                "Access catalog reconciled: "
                f"global_roles={role_count}, permissions={permission_count}."
            )
        )
