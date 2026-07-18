"""Preview the canonical PPP-adjusted platform subscription price per country (read-only).

The amount a school is CHARGED must equal ``base_price * country_multiplier`` (see
``apps.billing.services.resolve_platform_subscription_price``). The Stripe collection rail,
however, stores a Stripe Price *id* (``StripePlanPrice.stripe_price_id``) whose amount lives
in Stripe — so materializing these numbers into Stripe Price objects (or configuring a local
PSP) is an OPERATOR step that needs live processor access. This command emits the exact
reconciled numbers to configure, closing the "quoted == collected" loop at the level code
can: it never writes anything and never calls a processor.

Usage:
  python manage.py preview_platform_subscription_prices [--plan growth] [--countries US,IN,CM]
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.billing.models import CountryBillingProfile
from apps.siteconfig.models_platform_catalog import CountryMultiplier, Plan


class Command(BaseCommand):
    help = (
        "Preview canonical PPP-adjusted platform subscription prices per country "
        "(read-only; emits the numbers to configure in Stripe / a local PSP)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--plan", default="", help="Restrict to one Plan slug.")
        parser.add_argument(
            "--countries",
            default="",
            help="Comma-separated ISO country codes to restrict to (e.g. US,IN,CM).",
        )

    def handle(self, *args, **opts):
        plans = Plan.objects.filter(is_active=True)
        if opts["plan"]:
            plans = plans.filter(slug=opts["plan"])
        plans = list(plans.order_by("slug"))
        if not plans:
            self.stdout.write("No active plans match.")
            return

        countries = CountryMultiplier.objects.filter(is_active=True).order_by("country_code")
        wanted = {c.strip().upper() for c in opts["countries"].split(",") if c.strip()}
        if wanted:
            countries = countries.filter(country_code__in=wanted)
        countries = list(countries)

        currency_by_country = dict(
            CountryBillingProfile.objects.values_list("country_code", "currency_code")
        )

        for plan in plans:
            base = Decimal(str(getattr(plan, "base_price", None) or "0"))
            self.stdout.write(f"\nPlan {plan.slug}: base {base} (US anchor = 1.0x)")
            self.stdout.write(
                f"  {'country':<9}{'mult':>7}{'price':>13}{'currency':>10}"
            )
            for row in countries:
                mult = Decimal(str(row.multiplier))
                amount = (base * mult).quantize(Decimal("0.01"))
                currency = currency_by_country.get(row.country_code, "") or ""
                self.stdout.write(
                    f"  {row.country_code:<9}{mult:>7}{amount:>13}{currency:>10}"
                )
        self.stdout.write(
            "\nThese are the amounts to configure as Stripe Price objects / local-PSP "
            "prices so the collected amount equals the quoted amount."
        )
