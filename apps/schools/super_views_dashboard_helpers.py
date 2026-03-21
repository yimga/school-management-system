"""
Shared helpers for super dashboard and exports (BR-12 split from super_views).
"""

from __future__ import annotations

from django.core.exceptions import ObjectDoesNotExist
from django.urls import NoReverseMatch, reverse
from django.utils import timezone


def selected_system_names(school) -> list[str]:
    """
    Return selected education-system names for a school.
    Handles RelatedManager or list-like prefetched collections.
    """
    tenant_systems = getattr(school, "tenant_systems", None)
    if hasattr(tenant_systems, "all"):
        tenant_systems = tenant_systems.all()
    if not tenant_systems:
        return []
    return [ts.system.name for ts in tenant_systems if getattr(ts, "system", None)]


def safe_command_center_url() -> str:
    try:
        return reverse("super:command_center")
    except NoReverseMatch:
        return ""


def safe_registry_url() -> str:
    """Reverse to super registries overview when registered; else empty string."""
    try:
        return reverse("super:registries_overview")
    except NoReverseMatch:
        return ""


def brand_profile_for_school(school):
    try:
        return school.brand_profile
    except (AttributeError, ObjectDoesNotExist):
        return None


def education_level_label(level, country_code: str) -> str:
    labels = getattr(level, "country_labels", {}) or {}
    return str(
        labels.get(country_code)
        or getattr(level, "global_name", "")
        or getattr(level, "code", "")
    )


def education_system_type_label(system_type, country_code: str) -> str:
    labels = getattr(system_type, "country_labels", {}) or {}
    return str(
        labels.get(country_code)
        or getattr(system_type, "name", "")
        or getattr(system_type, "code", "")
    )


def status_tone(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"critical", "past_due", "past due", "suspended", "error", "open"}:
        return "danger"
    if normalized in {"warning", "acknowledged", "mitigated", "trialing", "pending"}:
        return "warning"
    if normalized in {"healthy", "active", "resolved", "success", "verified"}:
        return "success"
    return "neutral"


def safe_percentage(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 1)


def parse_month_param(request):
    """Parse ?month=YYYY-MM; return first day of that month or current month."""
    from datetime import date

    month_str = request.GET.get("month")
    if not month_str:
        return timezone.now().date().replace(day=1)
    try:
        year, month = int(month_str[:4]), int(month_str[5:7])
        if 1 <= month <= 12 and year >= 2020 and year <= 2100:
            return date(year, month, 1)
    except (ValueError, TypeError, IndexError):
        pass
    return timezone.now().date().replace(day=1)


def month_options(last_n=12):
    """Return list of (value 'YYYY-MM', label 'Month YYYY') for last N months (current first)."""
    now = timezone.now().date()
    first = now.replace(day=1)
    options = []
    for _ in range(last_n):
        options.append((first.strftime("%Y-%m"), first.strftime("%B %Y")))
        if first.month == 1:
            first = first.replace(year=first.year - 1, month=12, day=1)
        else:
            first = first.replace(month=first.month - 1, day=1)
    return options


def get_super_dashboard_section_order(user):
    """Return the section order for the super dashboard (per-user, from DB)."""
    from apps.runtime_blueprints.models import (
        SuperAdminDashboardPreference,
        SUPER_DASHBOARD_DEFAULT_SECTION_ORDER,
    )

    if not user or not user.is_authenticated:
        return list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    pref = SuperAdminDashboardPreference.objects.filter(user=user).first()
    if not pref:
        return list(SUPER_DASHBOARD_DEFAULT_SECTION_ORDER)
    return pref.get_section_order()

