"""
Promote an existing user to a full platform super-admin in ONE consistent step.

Why this exists
---------------
The platform has two independent notions of "super admin":

  1. The RBAC role ``User.role = "SUPERADMIN"`` — what the admin role dropdown sets.
  2. Django's ``is_staff`` / ``is_superuser`` boolean flags — a SEPARATE system.

Assigning the SUPERADMIN *role* alone does NOT set the Django flags (there is no
sync — the codified link only runs the other way, superuser -> role). Operator and
back-office surfaces such as ``/siteconfig/console/`` gate on ``is_staff``/``is_superuser``,
so a role-only SUPERADMIN fails the gate and Django's ``user_passes_test`` bounces
them back to ``/authentication/login/?next=...`` — an endless login/MFA loop with no
error. ``is_superuser=True`` is the true master switch: it bypasses RBAC checks,
passes the ``is_staff or is_superuser`` gates, AND grants break-glass access on tenant
hosts (see ``apps/accounts/middleware.py::TenantHostControlPlaneIsolationMiddleware``).

This command sets all three signals together (``is_staff``, ``is_superuser``,
``role=SUPERADMIN``) so nobody is ever left half-provisioned. It is idempotent.

Usage
-----
    python manage.py promote_superadmin <username>
    python manage.py promote_superadmin --email someone@example.com
    python manage.py promote_superadmin <username> --dry-run
"""

from django.contrib.auth import get_user_model
from django.core.management import BaseCommand, CommandError
from django.db import DatabaseError

from apps.accounts.superadmin_service import (
    apply_superadmin_change,
    compute_superadmin_changes,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Promote an existing user to a full platform super-admin: sets is_staff, "
        "is_superuser, is_active and role=SUPERADMIN together (idempotent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            nargs="?",
            default=None,
            help="Username of the user to promote (case-insensitive).",
        )
        parser.add_argument(
            "--email",
            default=None,
            help="Look the user up by email instead of username.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without saving anything.",
        )

    def handle(self, *args, **options):
        username = (options.get("username") or "").strip()
        email = (options.get("email") or "").strip()
        dry_run = bool(options.get("dry_run"))

        if not username and not email:
            raise CommandError("Provide a <username> or --email <address>.")

        try:
            user = self._resolve_user(username, email)
        except DatabaseError as exc:
            raise CommandError(f"Database error while looking up the user: {exc}")

        if user is None:
            raise CommandError(f"No user found matching '{username or email}'.")

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"User: {user.get_username()} <{user.email or 'no-email'}>"
            )
        )
        self.stdout.write(
            "  before: is_staff=%s is_superuser=%s is_active=%s role=%s"
            % (
                user.is_staff,
                user.is_superuser,
                user.is_active,
                getattr(user, "role", "n/a"),
            )
        )

        self._report_memberships(user)

        changes = compute_superadmin_changes(user)
        if not changes:
            self.stdout.write(
                self.style.SUCCESS("Already a full super-admin — nothing to do.")
            )
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run — would apply:"))
            for change in changes:
                self.stdout.write("  " + change)
            self.stdout.write("Re-run without --dry-run to apply.")
            return

        apply_superadmin_change(user)

        self.stdout.write(
            "  after:  is_staff=%s is_superuser=%s is_active=%s role=%s"
            % (
                user.is_staff,
                user.is_superuser,
                user.is_active,
                getattr(user, "role", "n/a"),
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Promoted '%s' to a full platform super-admin. They can now reach "
                "/siteconfig/console/ and navigate the platform end-to-end."
                % user.get_username()
            )
        )

    def _resolve_user(self, username, email):
        """Find the user by username (case-insensitive), falling back to email."""
        if username:
            found = User.objects.filter(username__iexact=username).first()
            if found is not None:
                return found
            if "@" in username:
                return User.objects.filter(email__iexact=username).first()
            return None
        return User.objects.filter(email__iexact=email).first()

    def _report_memberships(self, user):
        """Informational: is_superuser overrides the tenant-scoped control-plane
        carve-out, but a pure platform operator normally holds no tenant membership,
        so surface any so the operator can decide whether to keep them."""
        try:
            memberships = list(user.school_memberships.select_related("school")[:10])
        except (DatabaseError, AttributeError):
            return
        if not memberships:
            return
        labels = ", ".join(
            f"{m.school} (role={m.role}, owner={m.is_school_owner})" for m in memberships
        )
        self.stdout.write(
            self.style.WARNING("  note: user holds SchoolMembership(s): " + labels)
        )
        self.stdout.write(
            "        is_superuser=True still grants full access (god-mode overrides the "
            "tenant-scoped carve-out); a pure platform operator normally has no tenant "
            "membership."
        )
