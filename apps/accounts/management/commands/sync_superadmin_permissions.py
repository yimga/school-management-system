"""Reconcile the global SUPERADMIN access role with the full permission catalog.

Runs automatically on ``post_migrate``; this command exists for a box whose
migrations were applied before the reconciliation shipped, and for ``--check``
in a deploy gate.
"""

from django.core.management import BaseCommand

from apps.accounts.superadmin_sync import sync_superadmin_role_permissions


class Command(BaseCommand):
    help = "Grant every Permission to the global SUPERADMIN access role (additive)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report drift and exit non-zero instead of writing grants.",
        )

    def handle(self, *args, **options):
        if options.get("check"):
            from apps.accounts.models import AccessRole, Permission
            from apps.accounts.superadmin import SUPERADMIN_ROLE_CODE

            role = AccessRole.objects.filter(
                code=SUPERADMIN_ROLE_CODE, school__isnull=True
            ).first()
            if role is None:
                self.stderr.write(
                    self.style.ERROR("No global SUPERADMIN access role exists.")
                )
                raise SystemExit(1)
            held = set(role.permissions.values_list("code", flat=True))
            missing = sorted(
                set(Permission.objects.values_list("code", flat=True)) - held
            )
            if missing:
                self.stderr.write(
                    self.style.ERROR(
                        f"SUPERADMIN is missing {len(missing)} code(s): "
                        + ", ".join(missing)
                    )
                )
                raise SystemExit(1)
            self.stdout.write(
                self.style.SUCCESS(f"OK   SUPERADMIN holds all {len(held)} code(s).")
            )
            return
        added = sync_superadmin_role_permissions()
        if added:
            self.stdout.write(
                self.style.SUCCESS(f"Granted {added} code(s) to the SUPERADMIN role.")
            )
        else:
            self.stdout.write(self.style.SUCCESS("SUPERADMIN already holds every code."))
