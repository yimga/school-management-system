from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.siteconfig.models import SiteSettings

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
    help = "Seed finance defaults (Cameroon OHADA compliance profile + chart of accounts)."

    @transaction.atomic
    def handle(self, *args, **options):
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

        generic, _ = ComplianceProfile.objects.get_or_create(
            name="Generic Global",
            country_code="WW",
            defaults={
                "currency_code": "USD",
                "currency_symbol": "$",
                "timezone": "UTC",
                "chart_template": ComplianceProfile.ChartTemplate.GENERIC,
                "min_wage": Decimal("0"),
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
        self._seed_accounts(generic)

        site = SiteSettings.get_solo()
        if not getattr(site, "compliance_profile_id", None):
            site.compliance_profile = cameroon
            site.save(update_fields=["compliance_profile"])

        self.stdout.write(self.style.SUCCESS("Finance defaults seeded."))

    def _seed_tax_brackets(self, profile: ComplianceProfile) -> None:
        brackets = [
            (Decimal("0"), Decimal("60000"), Decimal("0.00")),
            (Decimal("60000"), Decimal("200000"), Decimal("0.10")),
            (Decimal("200000"), Decimal("500000"), Decimal("0.20")),
            (Decimal("500000"), None, Decimal("0.30")),
        ]
        TaxBracket.objects.filter(profile=profile).delete()
        for lower, upper, rate in brackets:
            TaxBracket.objects.create(
                profile=profile,
                lower_bound=lower,
                upper_bound=upper,
                rate=rate,
            )

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
