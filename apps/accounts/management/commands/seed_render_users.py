"""
Create or update admin, teacher1, and Parent1 with the same password.
Use as Release Command on Render so login works after every deploy.

Requires ADMIN_PASSWORD in environment. Example Release Command:
  python manage.py migrate --noinput && python manage.py seed_render_users
"""
import os
from django.core.management import BaseCommand, call_command


class Command(BaseCommand):
    help = (
        "Create/update admin, teacher1, and Parent1 using ADMIN_PASSWORD. "
        "Use after migrate in Render Release Command."
    )

    def handle(self, *args, **options):
        password = (os.environ.get("ADMIN_PASSWORD") or "").strip()
        if not password:
            self.stderr.write(
                self.style.ERROR(
                    "ADMIN_PASSWORD is not set. Set it in Render Environment and redeploy."
                )
            )
            return
        call_command("ensure_superuser", "--no-input", "--password", password, verbosity=1)
        call_command(
            "create_teacher_parent_accounts",
            "--teacher-username", "teacher1",
            "--parent-username", "Parent1",
            "--principal-username", "principal1",
            "--password", password,
            verbosity=1,
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Seed users ready. Log in with admin, teacher1, Parent1, or principal1 / your ADMIN_PASSWORD."
            )
        )
