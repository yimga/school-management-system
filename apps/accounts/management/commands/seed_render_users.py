"""
Ensure platform super-admin, one tenant admin, and optionally seed tenant demo users.
Use as Release Command on Render so login works after every deploy.

- Super-admin: always created/updated with username=admin, password=admin (manager/super only).
- Tenant admin: always created/updated with configurable username/password and linked to a chosen tenant.
- Tenant demo users (teacher1, Parent1, principal1): created only when ADMIN_PASSWORD is set;
  that password is used for tenant users only (not for admin).

Example Release Command:
  python manage.py migrate --noinput && python manage.py seed_render_users
"""

import os
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = (
        "Ensure super-admin admin/admin (platform). If ADMIN_PASSWORD is set, also create/update "
        "tenant demo users (teacher1, Parent1, principal1) with that password. Use after migrate in Render."
    )

    def handle(self, *args, **options):
        # Ensure tenant DB schema matches models (e.g. people.0040 updated_at) before any
        # TeacherProfile query. Fixes Render predeploy when migrate step was skipped or a
        # tenant schema was created after the last migrate_schemas --tenant.
        from django.conf import settings

        if getattr(settings, "USE_DJANGO_TENANTS", False):
            self.stdout.write("Running migrate_schemas --tenant (before user seed)...")
            call_command("migrate_schemas", "--tenant", "--noinput", verbosity=1)

        tenant_slug = (os.environ.get("DEFAULT_TENANT_SLUG") or "").strip()
        tenant_admin_username = (
            os.environ.get("DEFAULT_TENANT_ADMIN_USERNAME") or "tenant_admin"
        ).strip()
        tenant_admin_password = (
            os.environ.get("DEFAULT_TENANT_ADMIN_PASSWORD") or "Sch00l_1234"
        ).strip()

        # 1. Always ensure platform super-admin: username=admin, password=admin (no env override)
        call_command(
            "ensure_superuser",
            "--username",
            "admin",
            "--password",
            "admin",
            "--email",
            "admin@example.com",
            "--no-input",
            verbosity=options.get("verbosity", 1),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Super-admin ready: log in with admin / admin at /authentication/login/ or /super/."
            )
        )

        # 2. Tenant admin: configurable bootstrap account for one tenant login surface.
        ensure_tenant_admin_args = [
            "ensure_default_tenant_admin",
            "--username",
            tenant_admin_username,
            "--password",
            tenant_admin_password,
        ]
        if tenant_slug:
            ensure_tenant_admin_args.extend(["--slug", tenant_slug])
        call_command(*ensure_tenant_admin_args, verbosity=options.get("verbosity", 1))

        # 3. Tenant demo users: only when ADMIN_PASSWORD is set (separate credential)
        tenant_password = (os.environ.get("ADMIN_PASSWORD") or "").strip()
        if tenant_password:
            call_command(
                "create_teacher_parent_accounts",
                "--teacher-username",
                "teacher1",
                "--parent-username",
                "Parent1",
                "--principal-username",
                "principal1",
                "--password",
                tenant_password,
                verbosity=options.get("verbosity", 1),
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Tenant demo users (teacher1, Parent1, principal1) ready; password from ADMIN_PASSWORD."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "ADMIN_PASSWORD not set; tenant demo users (teacher1, Parent1, principal1) not created. "
                    "Set ADMIN_PASSWORD in Render Environment to seed them."
                )
            )
