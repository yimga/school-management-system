"""
Ensure platform super-admin (admin/admin), Gilead tenant admin, and optionally seed tenant demo users.
Use as Release Command on Render so login works after every deploy.

- Super-admin: always created/updated with username=admin, password=admin (manager/super only).
- Gilead tenant admin: always created/updated with username=gilead_admin, password=Sch00l_1234,
  linked to school gilead-school (for tenant login).
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
        # 1. Always ensure platform super-admin: username=admin, password=admin (no env override)
        call_command(
            "ensure_superuser",
            "--username", "admin",
            "--password", "admin",
            "--email", "admin@example.com",
            "--no-input",
            verbosity=options.get("verbosity", 1),
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Super-admin ready: log in with admin / admin at /authentication/login/ or /super/."
            )
        )

        # 2. Gilead tenant admin: gilead_admin / Sch00l_1234 (for tenant subdomain or /t/gilead-school/...)
        call_command(
            "ensure_gilead_admin",
            verbosity=options.get("verbosity", 1),
        )

        # 3. Tenant demo users: only when ADMIN_PASSWORD is set (separate credential)
        tenant_password = (os.environ.get("ADMIN_PASSWORD") or "").strip()
        if tenant_password:
            call_command(
                "create_teacher_parent_accounts",
                "--teacher-username", "teacher1",
                "--parent-username", "Parent1",
                "--principal-username", "principal1",
                "--password", tenant_password,
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
