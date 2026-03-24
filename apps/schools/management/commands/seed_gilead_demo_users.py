"""
Deprecated alias — use ``seed_demo_tenant_users`` (RunMyCampus-neutral defaults).

Legacy behaviour preserved: targets first active school whose slug or subdomain
matches the historical demo tenant pattern; creates legacy-prefixed admin/teacher/parent users.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from apps.schools.demo_user_seeding import resolve_demo_school, seed_demo_users_for_school

# Historical demo tenant match (substring only in management command — not in apps/ lint paths).
_LEGACY_DEMO_Q = Q(slug__icontains="gilead") | Q(subdomain__icontains="gilead")


class Command(BaseCommand):
    help = (
        "[Deprecated] Legacy demo users. Prefer: python manage.py seed_demo_tenant_users"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            default="",
            help="School slug (default: match historical demo tenant slug/subdomain)",
        )
        parser.add_argument(
            "--password",
            default="Test1234",
            help="Password for all three users",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "This command is deprecated. Use: python manage.py seed_demo_tenant_users"
            )
        )
        slug = (options.get("school_slug") or "").strip()
        school = resolve_demo_school(
            school_slug=slug,
            extra_filter=None if slug else _LEGACY_DEMO_Q,
        )
        if not school:
            self.stderr.write(
                self.style.ERROR(
                    "No school found. Try --school-slug=your-slug or use seed_demo_tenant_users."
                )
            )
            return
        seed_demo_users_for_school(
            school,
            password=options["password"] or "Test1234",
            username_prefix="gilead",
            stdout=self.stdout,
            style=self.style,
        )
