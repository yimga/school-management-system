"""
Ensure a Gilead tenant admin user exists for the default school (gilead-school).
Use for local/testing and Render so tenant login works after deploy.

By default: creates/updates user gilead_admin with password Sch00l_1234 and links
them to the Gilead school as ADMIN. Does not change the platform superadmin (admin/admin).

With --use-admin-user: ensures the existing platform user "admin" is linked to Gilead
and sets their password to Sch00l_1234 (so tenant login is admin / Sch00l_1234).
Then manager login would also be admin/Sch00l_1234 unless you run ensure_superadmin
to reset manager to admin/admin.
"""
from django.core.management import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

GILEAD_SLUG = "gilead-school"
GILEAD_ADMIN_USERNAME = "gilead_admin"
GILEAD_ADMIN_PASSWORD = "Sch00l_1234"


class Command(BaseCommand):
    help = (
        "Ensure Gilead tenant admin exists. Default: gilead_admin / Sch00l_1234. "
        "Use --use-admin-user to set platform admin password to Sch00l_1234 and link to Gilead (admin / Sch00l_1234 on tenant)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--use-admin-user",
            action="store_true",
            help="Use the platform 'admin' user for Gilead (password set to Sch00l_1234). Manager will also use admin/Sch00l_1234 unless you run ensure_superadmin.",
        )

    def handle(self, *args, **options):
        try:
            School = __import__("apps.schools.models", fromlist=["School"]).School
            SchoolMembership = __import__(
                "apps.schools.models", fromlist=["SchoolMembership"]
            ).SchoolMembership
        except ImportError:
            self.stdout.write(
                self.style.WARNING("Schools app not available. Skipping Gilead admin.")
            )
            return

        school = School.objects.filter(slug=GILEAD_SLUG, is_active=True).first()
        if not school:
            self.stdout.write(
                self.style.WARNING(
                    "School with slug '%s' not found. Run migrations (e.g. 0012_seed_default_gilead_school)."
                    % GILEAD_SLUG
                )
            )
            return

        use_admin_user = options.get("use_admin_user", False)

        if use_admin_user:
            user = User.objects.filter(username="admin").first()
            if not user:
                self.stdout.write(
                    self.style.WARNING(
                        "User 'admin' not found. Run ensure_superadmin or seed_render_users first."
                    )
                )
                return
            user.set_password(GILEAD_ADMIN_PASSWORD)
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
                    "Gilead tenant admin (using platform admin): admin / %s. Log in at the Gilead tenant URL. Manager login is also admin/%s; run ensure_superadmin to reset manager to admin/admin."
                    % (GILEAD_ADMIN_PASSWORD, GILEAD_ADMIN_PASSWORD)
                )
            )
            return

        user, created = User.objects.get_or_create(
            username=GILEAD_ADMIN_USERNAME,
            defaults={
                "email": "gilead_admin@example.com",
                "first_name": "Gilead",
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
            user.email = user.email or "gilead_admin@example.com"
            user.save(update_fields=["role", "is_staff", "is_superuser", "is_active", "email"])

        user.set_password(GILEAD_ADMIN_PASSWORD)
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
                "Gilead tenant admin ready: %s / %s. Log in at the Gilead tenant URL (e.g. /authentication/login/ on tenant subdomain)."
                % (GILEAD_ADMIN_USERNAME, GILEAD_ADMIN_PASSWORD)
            )
        )
