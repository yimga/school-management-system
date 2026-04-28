"""
Orchestrate a full local/staging demo: academic seed + demo users.

  python manage.py ensure_demo_environment --school-slug=demo-school

Runs ``seed_demo`` then ``seed_demo_tenant_users`` for the same school.
Set RUNMYCAMPUS_DEMO_SANDBOX=1 (or DEMO_MODE=1) for the tenant UI banner.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run seed_demo and seed_demo_tenant_users for one school slug "
        "(demo data + demo.admin / demo.teacher / demo.parent)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school-slug",
            required=True,
            help="School slug (passed to seed_demo as --school and to seed_demo_tenant_users).",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Pass --reset to seed_demo (deletes prior demo domain data; keeps superusers).",
        )
        parser.add_argument(
            "--password",
            default="Test1234",
            help="Password for seed_demo_tenant_users (default: Test1234).",
        )
        parser.add_argument(
            "--username-prefix",
            default="demo",
            help="Username prefix for seed_demo_tenant_users (default: demo).",
        )

    def handle(self, *args, **options):
        slug = (options.get("school_slug") or "").strip()
        if not slug:
            self.stderr.write(self.style.ERROR("--school-slug is required."))
            return
        seed_kwargs = {"school": slug}
        if options.get("reset"):
            seed_kwargs["reset"] = True
        self.stdout.write("Running seed_demo …")
        call_command("seed_demo", **seed_kwargs)
        self.stdout.write("Running seed_demo_tenant_users …")
        call_command(
            "seed_demo_tenant_users",
            school_slug=slug,
            password=options.get("password") or "Test1234",
            username_prefix=options.get("username_prefix") or "demo",
        )
        self.stdout.write(
            self.style.SUCCESS("Demo environment ready for school slug: %s" % slug)
        )
