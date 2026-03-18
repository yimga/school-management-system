"""
Ensure a tenant admin user exists for a given school (by slug or first active).
Platform-neutral; use --slug or DEFAULT_TENANT_SLUG to target a tenant.
"""

import os

from django.core.management import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

DEFAULT_TENANT_ADMIN_USERNAME = os.getenv(
    "DEFAULT_TENANT_ADMIN_USERNAME", "tenant_admin"
)
DEFAULT_TENANT_ADMIN_PASSWORD = os.getenv(
    "DEFAULT_TENANT_ADMIN_PASSWORD", "ChangeMe_1234"
)


class Command(BaseCommand):
    help = (
        "Ensure a tenant admin user exists for the given tenant (--slug or first active). "
        "Use --username/--password to set credentials; --use-admin-user to link platform admin."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--slug",
            default=(os.getenv("DEFAULT_TENANT_SLUG") or "").strip(),
            help="Tenant slug. Defaults to DEFAULT_TENANT_SLUG when set, otherwise the first active tenant.",
        )
        parser.add_argument(
            "--username",
            default=DEFAULT_TENANT_ADMIN_USERNAME,
            help="Tenant admin username.",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_TENANT_ADMIN_PASSWORD,
            help="Tenant admin password.",
        )
        parser.add_argument(
            "--use-admin-user",
            action="store_true",
            help="Use the existing platform 'admin' user as the tenant admin for the selected tenant.",
        )

    def handle(self, *args, **options):
        try:
            School = __import__("apps.schools.models", fromlist=["School"]).School
            SchoolMembership = __import__(
                "apps.schools.models", fromlist=["SchoolMembership"]
            ).SchoolMembership
        except ImportError:
            self.stdout.write(
                self.style.WARNING(
                    "Schools app not available. Skipping tenant admin bootstrap."
                )
            )
            return

        slug = (options.get("slug") or "").strip().lower()
        if slug:
            school = School.objects.filter(slug=slug, is_active=True).first()
        else:
            school = (
                School.objects.filter(is_active=True)
                .order_by("created_at", "id")
                .first()
            )
        if not school:
            self.stdout.write(
                self.style.WARNING(
                    "No active tenant found. Provide --slug or create a tenant first."
                )
            )
            return

        use_admin_user = options.get("use_admin_user", False)
        tenant_admin_username = (
            options.get("username") or DEFAULT_TENANT_ADMIN_USERNAME
        ).strip()
        tenant_admin_password = (
            options.get("password") or DEFAULT_TENANT_ADMIN_PASSWORD
        ).strip()

        if use_admin_user:
            user = User.objects.filter(username="admin").first()
            if not user:
                self.stdout.write(
                    self.style.WARNING(
                        "User 'admin' not found. Run ensure_superuser or seed_render_users first."
                    )
                )
                return
            user.set_password(tenant_admin_password)
            user.save()
            SchoolMembership.objects.get_or_create(
                user=user,
                school=school,
                defaults={"role": "ADMIN", "is_primary": True},
            )
            membership = SchoolMembership.objects.get(user=user, school=school)
            if membership.role != "ADMIN" or not membership.is_primary:
                membership.role = "ADMIN"
                membership.is_primary = True
                membership.save(update_fields=["role", "is_primary"])
            self.stdout.write(
                self.style.SUCCESS(
                    "Tenant admin ready for %s using platform admin: admin / %s."
                    % (school.slug, tenant_admin_password)
                )
            )
            return

        user, created = User.objects.get_or_create(
            username=tenant_admin_username,
            defaults={
                "email": f"{tenant_admin_username}@example.com",
                "first_name": school.name.split(" ")[0] if school.name else "Tenant",
                "last_name": "Admin",
                "role": User.Role.ADMIN,
                "is_staff": True,
                "is_superuser": False,
                "is_active": True,
            },
        )
        if not created:
            user.role = User.Role.ADMIN
            user.is_staff = True
            user.is_superuser = False
            user.is_active = True
            user.email = user.email or f"{tenant_admin_username}@example.com"
            user.save(
                update_fields=["role", "is_staff", "is_superuser", "is_active", "email"]
            )

        user.set_password(tenant_admin_password)
        user.save()

        SchoolMembership.objects.get_or_create(
            user=user,
            school=school,
            defaults={"role": "ADMIN", "is_primary": True},
        )
        membership = SchoolMembership.objects.get(user=user, school=school)
        if membership.role != "ADMIN" or not membership.is_primary:
            membership.role = "ADMIN"
            membership.is_primary = True
            membership.save(update_fields=["role", "is_primary"])

        self.stdout.write(
            self.style.SUCCESS(
                "Tenant admin ready for %s: %s / %s."
                % (school.slug, tenant_admin_username, tenant_admin_password)
            )
        )
