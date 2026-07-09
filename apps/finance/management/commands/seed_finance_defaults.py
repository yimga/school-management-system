from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.platform_runtime.helpers import (
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)

from apps.finance.payment_region_catalog import ensure_canonical_region_payment_profiles

from ...models import ComplianceProfile, ContributionRule, LedgerAccount, TaxBracket


OHADA_ACCOUNTS = [
    ("101", "Capital", LedgerAccount.AccountType.EQUITY),
    ("106", "Reserves", LedgerAccount.AccountType.EQUITY),
    ("120", "Net Result", LedgerAccount.AccountType.EQUITY),
    ("218", "Equipment", LedgerAccount.AccountType.ASSET),
    ("401", "Trade Payables", LedgerAccount.AccountType.LIABILITY),
    ("411", "Student Receivables", LedgerAccount.AccountType.ASSET),
    ("512", "Bank", LedgerAccount.AccountType.ASSET),
    ("514", "Mobile Money", LedgerAccount.AccountType.ASSET),
    ("531", "Cash", LedgerAccount.AccountType.ASSET),
    ("601", "Purchases", LedgerAccount.AccountType.EXPENSE),
    ("611", "Purchases and Services", LedgerAccount.AccountType.EXPENSE),
    ("621", "Staff Costs", LedgerAccount.AccountType.EXPENSE),
    ("701", "Sales of Services", LedgerAccount.AccountType.INCOME),
    ("706", "Tuition Revenue", LedgerAccount.AccountType.INCOME),
    ("708", "Other Revenue", LedgerAccount.AccountType.INCOME),
    ("755", "Grants and Subsidies", LedgerAccount.AccountType.INCOME),
]


class Command(BaseCommand):
    help = (
        "Seed finance defaults. By default seeds only the neutral 'Generic Global' "
        "ComplianceProfile and wires it as the platform RuntimeDefaults. Pass --include-cameroon "
        "(or --regions CM,...) to additionally seed regional presets like Cameroon OHADA."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be created without writing.",
        )
        parser.add_argument(
            "--include-cameroon",
            action="store_true",
            help=(
                "Also seed the Cameroon OHADA ComplianceProfile (chart of accounts, CNPS, "
                "income-tax brackets, FCFA labor defaults). Off by default so US/UK/IN/AE "
                "tenants don't inherit a Cameroon profile."
            ),
        )

    @transaction.atomic
    def handle(self, *args, **options):
        include_cameroon = options.get("include_cameroon", False)
        if options.get("dry_run"):
            extras = "+ Cameroon OHADA preset" if include_cameroon else "(no regional presets)"
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run: would ensure Generic Global ComplianceProfile {extras}, "
                    "wire RuntimeDefaults to Generic Global."
                )
            )
            return

        generic, _ = ComplianceProfile.objects.get_or_create(
            name="Generic Global",
            country_code="WW",
            defaults={
                "currency_code": "USD",
                "currency_symbol": "$",
                "timezone": "UTC",
                "chart_template": ComplianceProfile.ChartTemplate.GENERIC,
                "min_wage": Decimal("0"),
                "default_hours_per_week": Decimal("0"),
                "overtime_multiplier": Decimal("1.5"),
                "annual_leave_days": 0,
                "maternity_leave_days": 0,
                "is_active": True,
            },
        )
        self._seed_accounts(generic)

        cameroon = None
        if include_cameroon:
            cameroon, _ = ComplianceProfile.objects.get_or_create(
                name="Cameroon OHADA",
                country_code="CM",
                defaults={
                    "currency_code": "XAF",
                    "currency_symbol": "XAF",
                    "timezone": "Africa/Douala",
                    "chart_template": ComplianceProfile.ChartTemplate.OHADA,
                    "min_wage": Decimal("60000"),
                    "default_hours_per_week": Decimal("40"),
                    "overtime_multiplier": Decimal("1.5"),
                    "annual_leave_days": 21,
                    "maternity_leave_days": 84,
                    "is_active": True,
                },
            )
            self._seed_tax_brackets(cameroon)
            self._seed_contributions(cameroon)
            self._seed_accounts(cameroon)

        region_seed = ensure_canonical_region_payment_profiles()
        if region_seed.get("skipped"):
            self.stdout.write(
                self.style.WARNING(
                    "Payment region profiles skipped (finance PaymentRail tables missing). "
                    "Apply migrations, then re-run: python manage.py seed_finance_defaults "
                    "or call ensure_canonical_region_payment_profiles()."
                )
            )

        # Wire platform RuntimeDefaults to the neutral 'Generic Global' profile rather than
        # Cameroon — this is the profile a fresh tenant inherits, so it MUST be country-neutral.
        # config-resolver-allow: write-path singleton (create=True provisioning; record mutated via apply_feature_control_state)
        site = get_platform_site_settings_record(create=True)
        if site is not None:
            from apps.platform_runtime.models import RuntimeDefaults

            rd = (
                RuntimeDefaults.objects.filter(pk=1)
                .only("compliance_profile_id")
                .first()
            )
            if rd is None or not rd.compliance_profile_id:
                site.apply_feature_control_state(
                    field_updates={"compliance_profile_id": generic.pk},
                )
                invalidate_effective_site_settings_cache()

        self.stdout.write(self.style.SUCCESS("Finance defaults seeded (Generic Global)."))
        if include_cameroon and cameroon is not None:
            self.stdout.write(self.style.SUCCESS("Cameroon OHADA preset also seeded."))

    def _seed_tax_brackets(self, profile: ComplianceProfile) -> None:
        brackets = [
            (Decimal("0"), Decimal("60000"), Decimal("0.00")),
            (Decimal("60000"), Decimal("200000"), Decimal("0.10")),
            (Decimal("200000"), Decimal("500000"), Decimal("0.20")),
            (Decimal("500000"), None, Decimal("0.30")),
        ]
        seen_lower_bounds = []
        for lower, upper, rate in brackets:
            TaxBracket.objects.update_or_create(
                profile=profile,
                lower_bound=lower,
                defaults={"upper_bound": upper, "rate": rate},
            )
            seen_lower_bounds.append(lower)
        TaxBracket.objects.filter(profile=profile).exclude(
            lower_bound__in=seen_lower_bounds
        ).delete()

    def _seed_contributions(self, profile: ComplianceProfile) -> None:
        ContributionRule.objects.update_or_create(
            profile=profile,
            code="CNPS",
            defaults={
                "name": "CNPS",
                "employee_rate": Decimal("0.042"),
                "employer_rate": Decimal("0.1295"),
                "cap_amount": None,
            },
        )

    def _seed_accounts(self, profile: ComplianceProfile) -> None:
        for code, name, acc_type in OHADA_ACCOUNTS:
            LedgerAccount.objects.update_or_create(
                profile=profile,
                code=code,
                defaults={"name": name, "account_type": acc_type, "is_active": True},
            )
