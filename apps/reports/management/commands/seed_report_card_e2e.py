"""Seed published term report + hash ledger for tenant Playwright (metric #4)."""

from django.core.management.base import BaseCommand

from apps.reports.report_card_e2e_seed import seed_report_card_e2e


class Command(BaseCommand):
    help = (
        "Publish demo-school term report with hash ledger; writes var/e2e_report_card_fixture.json"
    )

    def add_arguments(self, parser):
        parser.add_argument("--school-slug", default="demo-school")
        parser.add_argument("--password", default="Test1234")
        parser.add_argument("--username-prefix", default="demo")

    def handle(self, *args, **options):
        seed_report_card_e2e(
            school_slug=options["school_slug"],
            password=options["password"],
            username_prefix=options["username_prefix"],
            stdout=self.stdout,
            style=self.style,
        )
