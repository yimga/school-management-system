"""Pre-authorise ONE box adoption, before the box exists (cloud side).

    python manage.py mint_claim_ticket --slug gilead-tech --user admin --days 14

For a scheduled install where nobody with cloud admin will be reachable while the
technician is on site. The printed ticket goes on the install sheet; the technician
runs `pair_box --claim <ticket>` and the box adopts itself with no approval step.

A ticket is NOT a credential. It buys exactly one auto-approved pairing for one named
school, it is spent the first time it is used, and every later attempt to use it is
counted and logged as an intrusion signal -- because the real box redeems once and
never again. That alarm is the property a long-lived RMC_EDGE_CREDENTIAL sitting in a
.env file can never give you.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Mint a single-use claim ticket that pre-authorises one box adoption."

    def add_arguments(self, parser):
        parser.add_argument("--slug", required=True, help="School slug.")
        parser.add_argument("--user", required=True, help="Username minting the ticket (must administer the school, or be staff).")
        parser.add_argument("--days", type=int, default=14, help="Ticket lifetime (default 14).")
        parser.add_argument("--label", default="", help="Note shown to whoever reviews tickets later.")

    def handle(self, *args, **options):
        from apps.schools.models import School
        from apps.sync_engine.pairing_service import mint_claim_ticket

        school = School.objects.filter(slug=options["slug"].strip()).first()
        if school is None:
            raise CommandError(f"No school with slug {options['slug']!r}.")
        user = get_user_model().objects.filter(username=options["user"].strip()).first()
        if user is None:
            raise CommandError(f"No user named {options['user']!r}.")

        result = mint_claim_ticket(
            school=school, minted_by=user, days=int(options["days"]), label=options["label"]
        )
        if not result.get("ok"):
            raise CommandError(
                {
                    "forbidden": f"{user.username} does not administer {school.slug} and is not staff.",
                    "school_required": "No school resolved.",
                }.get(result.get("error"), f"Could not mint: {result.get('error')}")
            )

        self.stdout.write(self.style.SUCCESS(
            f"Claim ticket for {school.slug}, expires {result['expires_at']}."
        ))
        self.stdout.write("")
        self.stdout.write("Ticket (shown ONCE — single use):")
        self.stdout.write(result["ticket"])
        self.stdout.write("")
        self.stdout.write("On the box:  python manage.py pair_box --claim <ticket> --wait")
