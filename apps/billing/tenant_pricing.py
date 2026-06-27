from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import DatabaseError

from apps.billing.models import CountryBillingProfile, TenantSubscription
from apps.billing.regional_pricing import compute_localized_price
from apps.billing.services import (
    compute_subscription_price_for_school,
    preview_subscription_commercial_terms,
)
from apps.siteconfig.models_platform_catalog import CountryMultiplier, Plan, PlanAddon


DEFAULT_BILLING_CYCLES = ["monthly", "annual", "school_year", "custom_contract"]
DEFAULT_PAYMENT_METHODS = ["card", "bank_transfer", "invoice"]
ACCESS_TIER_PAYMENT_METHODS = [
    "card",
    "bank_transfer",
    "mobile_money",
    "invoice",
    "purchase_order",
]


def _clean_list(value: Any, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(fallback)
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or list(fallback)


def _clean_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def resolve_school_country_code(school) -> str:
    if school is None:
        return ""
    resolver = getattr(school, "canonical_country_code", None)
    if callable(resolver):
        try:
            code = resolver()
            if code:
                return str(code).upper()[:2]
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass
    code = str(getattr(school, "country_code", "") or "").strip().upper()
    if code:
        return code[:2]
    region = getattr(school, "default_region", None)
    raw_region = str(getattr(region, "code", "") or getattr(school, "default_region_id", "") or "")
    if not raw_region:
        return ""
    try:
        from apps.siteconfig.global_catalog import GlobalGeoCatalog

        return (GlobalGeoCatalog.alpha2_for_country(raw_region) or raw_region).upper()[:2]
    except (ImportError, AttributeError, TypeError, ValueError, RuntimeError):
        return raw_region.upper()[:2]


def _country_registry_defaults(country_code: str) -> dict[str, str]:
    if not country_code:
        return {}
    try:
        from apps.registries.models import CountryRegistry

        row = (
            CountryRegistry.objects.filter(code__iexact=country_code, is_active=True)
            .only("code", "name", "default_currency", "default_language")
            .first()
        )
    except (ImportError, DatabaseError, AttributeError, RuntimeError, ValueError):
        row = None
    if row is None:
        return {}
    return {
        "name": row.name,
        "currency_code": row.default_currency or "USD",
        "invoice_locale": row.default_language or "",
    }


def _country_multiplier(country_code: str) -> CountryMultiplier | None:
    if not country_code:
        return None
    try:
        return CountryMultiplier.objects.filter(
            country_code__iexact=country_code,
            is_active=True,
        ).first()
    except (DatabaseError, AttributeError, RuntimeError, ValueError):
        return None


def country_billing_profile_for(country_code: str) -> dict[str, Any]:
    country_code = str(country_code or "").upper()[:2]
    if not country_code:
        country_code = "ZZ"
    registry = _country_registry_defaults(country_code)
    multiplier = _country_multiplier(country_code)
    try:
        profile = CountryBillingProfile.objects.filter(
            country_code__iexact=country_code,
            is_active=True,
        ).first()
    except (DatabaseError, AttributeError, RuntimeError, ValueError):
        profile = None

    zone = (getattr(multiplier, "zone", "") or "B").upper()
    if profile is None:
        payment_methods = ACCESS_TIER_PAYMENT_METHODS if zone == "C" else DEFAULT_PAYMENT_METHODS
        return {
            "country_code": country_code,
            "country_name": registry.get("name") or getattr(multiplier, "name", "") or country_code,
            "currency_code": registry.get("currency_code") or "USD",
            "market_tier": zone if zone in {"A", "B", "C"} else "B",
            "price_zone": zone,
            "public_price_mode": "LOCALIZED",
            "default_billing_cycles": list(DEFAULT_BILLING_CYCLES),
            "payment_methods": list(payment_methods),
            "tax_behavior": "EXCLUSIVE",
            "invoice_locale": registry.get("invoice_locale") or "en",
            "checkout_copy": {},
            "procurement_policy": {},
            "promotion_policy": {"annual_discount_percent": 10},
            "addon_policy": {},
            "metadata": {"source": "fallback_profile"},
            "is_configured": False,
        }

    return {
        "country_code": profile.country_code,
        "country_name": profile.country_name or registry.get("name") or profile.country_code,
        "currency_code": profile.currency_code or registry.get("currency_code") or "USD",
        "market_tier": profile.market_tier,
        "price_zone": profile.price_zone or zone,
        "public_price_mode": profile.public_price_mode,
        "default_billing_cycles": _clean_list(
            profile.default_billing_cycles, DEFAULT_BILLING_CYCLES
        ),
        "payment_methods": _clean_list(profile.payment_methods, DEFAULT_PAYMENT_METHODS),
        "tax_behavior": profile.tax_behavior,
        "invoice_locale": profile.invoice_locale or registry.get("invoice_locale") or "en",
        "checkout_copy": _clean_dict(profile.checkout_copy),
        "procurement_policy": _clean_dict(profile.procurement_policy),
        "promotion_policy": _clean_dict(profile.promotion_policy),
        "addon_policy": _clean_dict(profile.addon_policy),
        "metadata": _clean_dict(profile.metadata),
        "is_configured": True,
    }


def _student_count_for(school) -> int:
    if school is None:
        return 0
    try:
        from apps.people.models import Student

        return Student.objects.filter(school=school, is_active=True).count()
    except (ImportError, DatabaseError, AttributeError, RuntimeError, ValueError):
        return 0


def _annual_discount(profile: dict[str, Any]) -> Decimal:
    policy = _clean_dict(profile.get("promotion_policy"))
    try:
        raw = policy.get("annual_discount_percent", 10)
        value = Decimal(str(raw))
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("10")
    if value < 0:
        return Decimal("0")
    if value > 100:
        return Decimal("100")
    return value


def _plan_cycles(plan: Plan, profile: dict[str, Any]) -> list[str]:
    return _clean_list(getattr(plan, "billing_cycle_options", []), profile["default_billing_cycles"])


def _plan_payment_methods(plan: Plan, profile: dict[str, Any]) -> list[str]:
    return _clean_list(getattr(plan, "payment_method_options", []), profile["payment_methods"])


def _plan_card(plan: Plan, school, profile: dict[str, Any], student_count: int) -> dict[str, Any]:
    priced = {}
    if not getattr(plan, "requires_quote", False):
        try:
            priced = compute_subscription_price_for_school(
                school,
                plan,
                student_count=student_count,
            )
        except (ImportError, DatabaseError, AttributeError, RuntimeError, ValueError):
            priced = {}
    monthly_total = Decimal(str(priced.get("total", "0") or "0"))
    discount = _annual_discount(profile)
    annual_total = (monthly_total * Decimal("12") * (Decimal("100") - discount) / Decimal("100")).quantize(
        Decimal("0.01")
    )
    return {
        "slug": plan.slug,
        "name": plan.name,
        "audience": plan.audience,
        "summary": plan.tenant_summary,
        "display_order": plan.display_order,
        "requires_quote": plan.requires_quote,
        "billing_model": plan.billing_model,
        "monthly_total": monthly_total,
        "annual_total": annual_total,
        "currency_code": priced.get("currency_code") or profile["currency_code"],
        "tax": priced.get("tax", Decimal("0.00")),
        "tax_rate": priced.get("tax_rate", Decimal("0")),
        "billing_cycles": _plan_cycles(plan, profile),
        "payment_methods": _plan_payment_methods(plan, profile),
        "included_usage": _clean_dict(plan.included_usage),
        "support_policy": _clean_dict(plan.support_policy),
        "features": list(plan.included_features or []),
        "max_students": plan.max_students,
        "max_staff": plan.max_staff,
    }


def _addon_card(addon: PlanAddon, country_code: str, profile: dict[str, Any]) -> dict[str, Any]:
    override = addon.regional_price_override_for(country_code)
    priced = compute_localized_price(
        addon.price,
        country_code,
        currency_override=profile["currency_code"],
        sku_override=override,
    )
    return {
        "code": addon.code,
        "name": addon.name,
        "description": addon.description,
        "category": addon.category,
        "billing_unit": addon.billing_unit,
        "monthly_total": priced.total,
        "currency_code": priced.currency_code,
        "tax": priced.tax,
        "included_in_plan_codes": list(addon.included_in_plan_codes or []),
        "available_to_plan_codes": list(addon.available_to_plan_codes or []),
    }


def tenant_pricing_options(school) -> dict[str, Any]:
    country_code = resolve_school_country_code(school)
    profile = country_billing_profile_for(country_code)
    student_count = _student_count_for(school)
    subscription = (
        TenantSubscription.objects.filter(school=school)
        .select_related("plan")
        .order_by("-updated_at", "-created_at")
        .first()
        if school is not None
        else None
    )
    current_terms = None
    if subscription is not None:
        current_terms = preview_subscription_commercial_terms(subscription)

    plans = [
        _plan_card(plan, school, profile, student_count)
        for plan in Plan.objects.filter(is_active=True, tenant_visible=True).order_by(
            "display_order", "name"
        )
    ]
    addons = [
        _addon_card(addon, country_code, profile)
        for addon in PlanAddon.objects.filter(is_active=True, tenant_visible=True).order_by(
            "display_order", "name"
        )
    ]
    return {
        "country": profile,
        "student_count": student_count,
        "current_subscription": subscription,
        "current_terms": current_terms,
        "plans": plans,
        "addons": addons,
        "annual_discount_percent": _annual_discount(profile),
        "tenant_message": (
            "Choose a plan, billing cycle, and payment method that works in your country. "
            "Enterprise, ministry, sovereign, and sponsored terms stay configurable by operators."
        ),
    }
