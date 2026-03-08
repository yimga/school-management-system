"""
Create or fix a superuser when none exists. Use after migrate when user accounts
or admin credentials are not working (e.g. fresh DB, or users exist but none are superuser).

Same credentials work for:
- Portal/Backend login: /authentication/login/
- Django Admin: /admin/
"""
import os
from django.conf import settings
from django.core.management import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

# Custom User may have Role enum
SUPERADMIN_ROLE = getattr(User, "Role", None)
if SUPERADMIN_ROLE is not None and hasattr(SUPERADMIN_ROLE, "SUPERADMIN"):
    SUPERADMIN_ROLE_VALUE = SUPERADMIN_ROLE.SUPERADMIN
else:
    SUPERADMIN_ROLE_VALUE = None


def _sync_superuser_flags(user_model, username):
    """Ensure the user has is_staff, is_superuser, is_active so Configuration Engine access works."""
    u = user_model.objects.filter(username=username).first()
    if u and (not u.is_staff or not u.is_superuser or not u.is_active):
        u.is_staff = True
        u.is_superuser = True
        u.is_active = True
        u.save(update_fields=["is_staff", "is_superuser", "is_active"])
        return True
    return False


class Command(BaseCommand):
    help = (
        "Ensure at least one superuser exists. Creates one or promotes an existing user. "
        "Use when user accounts and admin credentials are not working."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default=os.environ.get("DEFAULT_SUPERUSER_USERNAME", "admin"),
            help="Username for the new superuser (default: admin or DEFAULT_SUPERUSER_USERNAME)",
        )
        parser.add_argument(
            "--password",
            default=os.environ.get("ADMIN_PASSWORD"),
            help="Password (default: ADMIN_PASSWORD env; in DEBUG only, fallback 'Sch00l_1234')",
        )
        parser.add_argument(
            "--email",
            default=os.environ.get("DEFAULT_SUPERUSER_EMAIL", "admin@example.com"),
            help="Email for the new superuser",
        )
        parser.add_argument(
            "--no-input",
            action="store_true",
            help="Use env/default password only; do not prompt",
        )

    def handle(self, *args, **options):
        username = (options["username"] or "").strip() or "admin"
        email = (options["email"] or "").strip() or "admin@example.com"
        password = (options["password"] or "").strip()

        # Check if User table exists (migrations may not have been run)
        try:
            has_superuser = User.objects.filter(is_superuser=True).exists()
        except Exception as e:
            err = str(e).lower()
            if "no such table" in err or "does not exist" in err or "relation" in err:
                self.stdout.write(
                    self.style.WARNING(
                        "Accounts User table not found. Run: python manage.py migrate"
                    )
                )
                return
            raise

        # When password is provided (e.g. ADMIN_PASSWORD on Render), always ensure this username exists and has this password so login works
        if has_superuser and password:
            existing_admin = User.objects.filter(username=username).first()
            if existing_admin:
                existing_admin.set_password(password)
                existing_admin.is_staff = True
                existing_admin.is_superuser = True
                existing_admin.is_active = True
                existing_admin.email = email or existing_admin.email
                if SUPERADMIN_ROLE_VALUE is not None and hasattr(existing_admin, "role"):
                    existing_admin.role = SUPERADMIN_ROLE_VALUE
                existing_admin.save()
                _sync_superuser_flags(User, username)
                self.stdout.write(
                    self.style.SUCCESS(
                        "Superuser '%s' password updated. Log in at /authentication/login/ or /admin/" % username
                    )
                )
                return
            # else: another user is superuser but not this username; fall through to create this username

        if has_superuser and not password:
            self.stdout.write(
                self.style.SUCCESS(
                    "A superuser already exists. To reset a password, run:\n"
                    "  python manage.py changepassword <username>"
                )
            )
            return

        if not password and settings.DEBUG:
            password = "Sch00l_1234"
            self.stdout.write(
                self.style.WARNING(
                    "Using default password 'Sch00l_1234' (DEBUG=True). "
                    "Change it: python manage.py changepassword " + username
                )
            )
        if not password:
            if options["no_input"]:
                self.stderr.write(
                    self.style.ERROR(
                        "No password set. Set ADMIN_PASSWORD env or use --password."
                    )
                )
                return
            from getpass import getpass

            password = getpass("Password for %s: " % username)
            if not password:
                self.stderr.write(self.style.ERROR("Password required."))
                return

        existing = User.objects.filter(username=username).first()
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    "User '%s' exists but is not a superuser. Promoting and setting password."
                    % username
                )
            )
            existing.set_password(password)
            existing.is_staff = True
            existing.is_superuser = True
            existing.is_active = True
            existing.email = email or existing.email
            if SUPERADMIN_ROLE_VALUE is not None and hasattr(existing, "role"):
                existing.role = SUPERADMIN_ROLE_VALUE
            existing.save()
            _sync_superuser_flags(User, username)
            self.stdout.write(
                self.style.SUCCESS(
                    "Superuser '%s' updated. Log in at /authentication/login/ or /admin/"
                    % username
                )
            )
            return

        User.objects.create_superuser(
            username=username,
            email=email or f"{username}@example.com",
            password=password,
        )
        u = User.objects.get(username=username)
        if SUPERADMIN_ROLE_VALUE is not None and hasattr(u, "role"):
            u.role = SUPERADMIN_ROLE_VALUE
            u.save(update_fields=["role"])
        _sync_superuser_flags(User, username)
        self.stdout.write(
            self.style.SUCCESS(
                "Superuser '%s' created. You can log in at:\n"
                "  Portal/Backend: /authentication/login/\n"
                "  Django Admin:   /admin/"
                % username
            )
        )
