"""
Seed demo admin / teacher / parent users for any active tenant (RunMyCampus-neutral).

  python manage.py seed_demo_tenant_users
  python manage.py seed_demo_tenant_users --school-slug=my-school

Default: first active school by created_at. Usernames: demo.admin, demo.teacher, demo.parent.
"""

from django.core.management.base import BaseCommand

from apps.schools.demo_user_seeding import resolve_demo_school, seed_demo_users_for_school


class Command(BaseCommand):
    help = (
        "Seed demo.admin, demo.teacher, demo.parent for a tenant (password Test1234 by default)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            default="",
            help="School slug (default: first active school)",
        )
        parser.add_argument(
            "--password",
            default="Test1234",
            help="Password for all three users",
        )
        parser.add_argument(
            "--username-prefix",
            default="demo",
            help="Prefix for usernames (default: demo → demo.admin, …)",
        )

    def handle(self, *args, **options):
        slug = (options.get("school_slug") or "").strip()
        school = resolve_demo_school(school_slug=slug, extra_filter=None)
        if not school:
            self.stderr.write(
                self.style.ERROR(
                    "No active school found. Create a school or pass --school-slug=."
                )
            )
            return
        seed_demo_users_for_school(
            school,
            password=options["password"] or "Test1234",
            username_prefix=options.get("username_prefix") or "demo",
            stdout=self.stdout,
            style=self.style,
        )
