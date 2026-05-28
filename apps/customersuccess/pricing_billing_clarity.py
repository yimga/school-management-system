"""Tenant billing estimate + marketing pricing crosswalk (CEZGP Lane 2 P10 / B6)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.urls import reverse

ROOT = Path(__file__).resolve().parents[2]


def _pricing_packages_payload() -> dict[str, Any]:
    path = ROOT / "apps" / "schools" / "data" / "pricing_packages.json"
    return json.loads(path.read_text(encoding="utf-8"))


def pricing_clarity_crosswalk(*, school=None) -> dict[str, Any]:
    """Map marketing packages to tenant subscription posture."""
    packages = _pricing_packages_payload().get("packages") or []
    marketing_url = ""
    packages_clarity_url = ""
    try:
        marketing_url = reverse("marketing_pricing")
        packages_clarity_url = reverse("marketing_pricing_packages_clarity")
    except Exception:
        pass

    subscription = None
    plan_name = ""
    status = ""
    billing_cycle = ""
    monthly_estimate = Decimal("0")
    annual_estimate = Decimal("0")
    student_count = 0

    if school is not None:
        try:
            from apps.billing.models import TenantSubscription
            from apps.billing.services import _subscription_amount

            subscription = (
                TenantSubscription.objects.filter(school=school)
                .select_related("plan")
                .order_by("-updated_at")
                .first()
            )
            if subscription is not None:
                plan_name = getattr(subscription.plan, "name", "") or subscription.plan_code or ""
                status = subscription.get_status_display()
                billing_cycle = subscription.get_billing_cycle_display()
                amount = _subscription_amount(subscription)
                if subscription.billing_cycle == TenantSubscription.BillingCycle.ANNUAL:
                    annual_estimate = amount
                    monthly_estimate = (amount / Decimal("12")).quantize(Decimal("0.01"))
                else:
                    monthly_estimate = amount
                    annual_estimate = (amount * Decimal("12")).quantize(Decimal("0.01"))
        except Exception:
            pass
        try:
            from apps.people.models import Student

            student_count = Student.objects.filter(school=school, is_active=True).count()
        except Exception:
            pass

    matched_package = None
    plan_key = (plan_name or "").strip().lower()
    for pkg in packages:
        if plan_key and plan_key in (pkg.get("slug") or "").lower():
            matched_package = pkg
            break
        if plan_key and plan_key in (pkg.get("name") or "").lower():
            matched_package = pkg
            break

    return {
        "marketing_pricing_url": marketing_url,
        "packages_clarity_url": packages_clarity_url,
        "packages": packages,
        "matched_package": matched_package,
        "subscription": subscription,
        "plan_name": plan_name,
        "subscription_status": status,
        "billing_cycle": billing_cycle,
        "monthly_estimate_display": monthly_estimate,
        "annual_estimate_display": annual_estimate,
        "student_count": student_count,
        "live_psp_caveat": _pricing_packages_payload().get("live_psp_caveat", ""),
    }


def tenant_billing_estimate_context(*, school) -> dict[str, Any]:
    crosswalk = pricing_clarity_crosswalk(school=school)
    crosswalk["tenant_billing_estimate"] = {
        "monthly": crosswalk["monthly_estimate_display"],
        "annual": crosswalk["annual_estimate_display"],
        "per_student_hint": (
            (crosswalk["monthly_estimate_display"] / crosswalk["student_count"]).quantize(
                Decimal("0.01")
            )
            if crosswalk["student_count"] and crosswalk["monthly_estimate_display"] > 0
            else None
        ),
    }
    return crosswalk
