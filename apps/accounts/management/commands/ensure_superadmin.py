"""
Create a superuser with username=admin, password=admin only if no user with
username 'admin' exists. Does not change any existing user or tenant credentials.

Use for Super-admin (manage all tenants) at /super/ when no admin account exists.

**Deprecated:** Prefer ensure_superuser (supports ADMIN_PASSWORD env, --username,
--password, and promotes existing users). This command remains available during
deprecation; see management_commands_inventory.md §5a.
"""
from django.core.management import BaseCommand
from django.contrib.auth import get_user_model

from apps.platform_runtime.management_utils import emit_command_deprecation

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Create superuser admin/admin only if username 'admin' does not exist. "
        "Does not modify any existing user or tenant. Deprecated: use ensure_superuser."
    )

    def handle(self, *args, **options):
        emit_command_deprecation(
            self.stdout,
            self.style,
            "ensure_superadmin is deprecated.",
            replacement="Use: python manage.py ensure_superuser (supports ADMIN_PASSWORD, --username, --password; promotes existing users).",
        )
        if User.objects.filter(username="admin").exists():
            self.stdout.write(
                self.style.WARNING("User 'admin' already exists. No changes made.")
            )
            return
        User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="admin",
        )
        admin_user = User.objects.get(username="admin")
        if getattr(User, "Role", None) is not None and hasattr(User.Role, "SUPERADMIN"):
            admin_user.role = User.Role.SUPERADMIN
            admin_user.save(update_fields=["role"])
        self.stdout.write(
            self.style.SUCCESS(
                "Superuser 'admin' created (password: admin). "
                "Log in at /authentication/login/ or /super/ (change password after first login)."
            )
        )
