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
        "CM",  # Cameroon — OHADA / MoMo corridor
        "NG",  # Nigeria — Paystack / Flutterwave dominant
        "GH",  # Ghana — MTN MoMo / Paystack
        "KE",  # Kenya — M-Pesa / Flutterwave
        "UG",  # Uganda — MTN MoMo / Flutterwave
        "TZ",  # Tanzania — M-Pesa / Tigo / Flutterwave
        "RW",  # Rwanda — MTN MoMo / Airtel Money
        "ZA",  # South Africa — Stripe / Flutterwave
        "CI",  # Côte d'Ivoire — Orange Money / MTN MoMo
        "SN",  # Senegal — Orange Money / Wave
        "CD",  # DRC — Orange Money / M-Pesa
    }
)


# Default rail seeds per ISO2 — primary + backup with mobile-money-first ordering
# where penetration justifies it; cards as fallback in markets where Stripe is live.
_RAIL_DEFAULTS: Final[dict[str, dict[str, dict[str, str]]]] = {
    "CM": {
        "primary": {"code": "cm-mtn", "label": "MTN MoMo", "kind": "MOBILE_MONEY"},
        "backup": {"code": "cm-orange", "label": "Orange Money", "kind": "MOBILE_MONEY"},
    },
    "NG": {
        "primary": {"code": "ng-paystack", "label": "Paystack", "kind": "CARD"},
        "backup": {"code": "ng-flutterwave", "label": "Flutterwave", "kind": "CARD"},
    },
    "GH": {
        "primary": {"code": "gh-mtn", "label": "MTN MoMo", "kind": "MOBILE_MONEY"},
        "backup": {"code": "gh-paystack", "label": "Paystack", "kind": "CARD"},
    },
    "KE": {
        "primary": {"code": "ke-mpesa", "label": "M-Pesa", "kind": "MOBILE_MONEY"},
        "backup": {"code": "ke-flutterwave", "label": "Flutterwave", "kind": "CARD"},
    },
    "UG": {
        "primary": {"code": "ug-mtn", "label": "MTN MoMo", "kind": "MOBILE_MONEY"},
        "backup": {"code": "ug-flutterwave", "label": "Flutterwave", "kind": "CARD"},
    },
    "TZ": {
        "primary": {"code": "tz-mpesa", "label": "M-Pesa", "kind": "MOBILE_MONEY"},
        "backup": {"code": "tz-flutterwave", "label": "Flutterwave", "kind": "CARD"},
    },
    "RW": {
        "primary": {"code": "rw-mtn", "label": "MTN MoMo", "kind": "MOBILE_MONEY"},
        "backup": {"code": "rw-airtel", "label": "Airtel Money", "kind": "MOBILE_MONEY"},
    },
    "ZA": {
        "primary": {"code": "za-stripe", "label": "Stripe", "kind": "CARD"},
        "backup": {"code": "za-flutterwave", "label": "Flutterwave", "kind": "CARD"},
    },
    "CI": {
        "primary": {"code": "ci-orange", "label": "Orange Money", "kind": "MOBILE_MONEY"},
        "backup": {"code": "ci-mtn", "label": "MTN MoMo", "kind": "MOBILE_MONEY"},
    },
    "SN": {
        "primary": {"code": "sn-orange", "label": "Orange Money", "kind": "MOBILE_MONEY"},
        "backup": {"code": "sn-wave", "label": "Wave", "kind": "MOBILE_MONEY"},
    },
    "CD": {
        "primary": {"code": "cd-orange", "label": "Orange Money", "kind": "MOBILE_MONEY"},
        "backup": {"code": "cd-mpesa", "label": "M-Pesa", "kind": "MOBILE_MONEY"},
    },
}


_REGION_NAMES: Final[dict[str, str]] = {
    "CM": "Cameroon default",
    "NG": "Nigeria default",
    "GH": "Ghana default",
    "KE": "Kenya default",
    "UG": "Uganda default",
    "TZ": "Tanzania default",
    "RW": "Rwanda default",
    "ZA": "South Africa default",
    "CI": "Côte d'Ivoire default",
    "SN": "Senegal default",
    "CD": "DR Congo default",
}


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

    rail_kind_map = {
        "MOBILE_MONEY": PaymentRail.RailKind.MOBILE_MONEY,
        "CARD": getattr(PaymentRail.RailKind, "CARD", PaymentRail.RailKind.MOBILE_MONEY),
        "BANK": getattr(PaymentRail.RailKind, "BANK", PaymentRail.RailKind.MOBILE_MONEY),
    }

    for iso2 in sorted(CANONICAL_PAYMENT_ORCHESTRATION_ISO2):
        rails = _RAIL_DEFAULTS.get(iso2)
        if not rails:
            raise NotImplementedError(
                f"Add rail defaults for {iso2!r} in _RAIL_DEFAULTS "
                "(expand alongside CANONICAL_PAYMENT_ORCHESTRATION_ISO2)."
            )
        primary_spec = rails["primary"]
        backup_spec = rails["backup"]
        primary, c1 = PaymentRail.objects.get_or_create(
            code=primary_spec["code"],
            defaults={
                "label": primary_spec["label"],
                "kind": rail_kind_map.get(primary_spec["kind"], PaymentRail.RailKind.MOBILE_MONEY),
            },
        )
        backup, c2 = PaymentRail.objects.get_or_create(
            code=backup_spec["code"],
            defaults={
                "label": backup_spec["label"],
                "kind": rail_kind_map.get(backup_spec["kind"], PaymentRail.RailKind.MOBILE_MONEY),
            },
        )
        rails_created += int(c1) + int(c2)
        _, created = RegionPaymentProfile.objects.get_or_create(
            country_code=iso2,
            defaults={
                "name": _REGION_NAMES.get(iso2, f"{iso2} default"),
                "primary_rail": primary,
                "backup_rail": backup,
            },
        )
        profiles_created += int(created)

    return {
        "rails_created": rails_created,
        "profiles_created": profiles_created,
    }
