"""
Canonical ISO 3166-1 alpha-2 regions that must have RegionPaymentProfile rows when seeded.

Commercial tier names (free/pro/enterprise) and BR-10 SKU bundles do not enumerate
countries — this module is the single machine list for payment-orchestration parity.
Expand CANONICAL_PAYMENT_ORCHESTRATION_ISO2 when first-class primary/backup rails ship
for additional markets (and extend seed_finance_defaults / rail defaults accordingly).
"""

from __future__ import annotations

from typing import Any, Final

from django.db import connection
from django.db.models import QuerySet

# finance.0057_offline_global_ops — required before PaymentRail / RegionPaymentProfile exist.
_PAYMENT_ORCHESTRATION_TABLES: Final[frozenset[str]] = frozenset(
    {
        "finance_paymentrail",
        "finance_regionpaymentprofile",
    }
)


def _finance_payment_orchestration_tables_ready() -> bool:
    """True when migrations that create rail/profile tables have been applied."""
    names = {t.lower() for t in connection.introspection.table_names()}
    return _PAYMENT_ORCHESTRATION_TABLES <= names

CANONICAL_PAYMENT_ORCHESTRATION_ISO2: Final[frozenset[str]] = frozenset(
    {
        "CM",  # Cameroon — OHADA / MoMo corridor (seed_finance_defaults Cameroon OHADA)
    }
)


def iso2_codes_missing_payment_profiles(
    *,
    queryset: QuerySet | None = None,
) -> list[str]:
    """Return sorted ISO2 codes in the catalog that have no RegionPaymentProfile row."""
    from apps.finance.models import RegionPaymentProfile

    qs = queryset if queryset is not None else RegionPaymentProfile.objects.all()
    present = set(qs.values_list("country_code", flat=True))
    return sorted(CANONICAL_PAYMENT_ORCHESTRATION_ISO2 - present)


def ensure_canonical_region_payment_profiles() -> dict[str, Any]:
    """
    Idempotent: ensure PaymentRail + RegionPaymentProfile exist for each catalog ISO2.

    Called from seed_finance_defaults so fresh environments satisfy catalog parity tests.

    If finance.0057 tables are not present yet (e.g. bootstrap before migrate), returns
    ``{"skipped": True, ...}`` so seed does not fail — run ``migrate`` then re-run seed
    or ``ensure_canonical_region_payment_profiles()`` once.
    """
    if not _finance_payment_orchestration_tables_ready():
        return {
            "skipped": True,
            "reason": "payment_orchestration_tables_missing_run_migrate_finance",
            "rails_created": 0,
            "profiles_created": 0,
        }

    from apps.finance.models import PaymentRail, RegionPaymentProfile

    profiles_created = 0
    rails_created = 0

    for iso2 in sorted(CANONICAL_PAYMENT_ORCHESTRATION_ISO2):
        if iso2 != "CM":
            raise NotImplementedError(
                "Add rail defaults for "
                f"{iso2!r} in ensure_canonical_region_payment_profiles "
                "(expand alongside CANONICAL_PAYMENT_ORCHESTRATION_ISO2)."
            )
        primary, c1 = PaymentRail.objects.get_or_create(
            code="cm-mtn",
            defaults={
                "label": "MTN MoMo",
                "kind": PaymentRail.RailKind.MOBILE_MONEY,
            },
        )
        backup, c2 = PaymentRail.objects.get_or_create(
            code="cm-orange",
            defaults={
                "label": "Orange Money",
                "kind": PaymentRail.RailKind.MOBILE_MONEY,
            },
        )
        rails_created += int(c1) + int(c2)
        _, created = RegionPaymentProfile.objects.get_or_create(
            country_code="CM",
            defaults={
                "name": "Cameroon default",
                "primary_rail": primary,
                "backup_rail": backup,
            },
        )
        profiles_created += int(created)

    return {
        "rails_created": rails_created,
        "profiles_created": profiles_created,
    }
