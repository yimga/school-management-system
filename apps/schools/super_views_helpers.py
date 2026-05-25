"""
Shared helpers for super_views and super_views_provisioning (BR-12 structural split).
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse

from apps.registries.models import CountryRegistry, SubdivisionRegistry
from apps.siteconfig.education_profile_engine import (
    ensure_region_for_country as ensure_region_for_country_record,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog


def slug_from_school_name(name: str) -> str:
    import re

    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:120] if s else "school"


def safe_school_timeline_url(school_id) -> str:
    try:
        return reverse("super:api_school_timeline", args=[school_id])
    except NoReverseMatch:
        return ""


def safe_tenant_360_url(school_id) -> str:
    try:
        return reverse("super:tenant_360", args=[school_id])
    except NoReverseMatch:
        return ""


# Underscore names: same behavior (tests and super_views re-export use these).
_safe_school_timeline_url = safe_school_timeline_url


def safe_school_admin_change_url(school_id) -> str:
    """Admin URLs are not part of the product surface; placeholder for legacy call sites."""
    return ""


_safe_school_admin_change_url = safe_school_admin_change_url


def safe_platform_incidents_url() -> str:
    """Reverse to observability incident console when registered; else empty string."""
    try:
        return reverse("platform_incidents_console")
    except NoReverseMatch:
        return ""


def canonical_country_alpha2(raw_country_code: str | None) -> str:
    normalized = GlobalGeoCatalog.normalize_country_code(raw_country_code)
    alpha2 = GlobalGeoCatalog.alpha2_for_country(normalized or raw_country_code)
    if alpha2:
        return alpha2.upper()
    raw = (raw_country_code or "").strip().upper()
    return raw if len(raw) == 2 else ""


def ensure_region_for_country(country_code: str, timezone_hint: str = "UTC"):
    return ensure_region_for_country_record(country_code, timezone_hint=timezone_hint)


def resolve_subdivision(
    country_code: str | None, *, subdivision_id=None, province_id=None
):
    alpha2 = canonical_country_alpha2(country_code)
    if subdivision_id not in (None, ""):
        try:
            return SubdivisionRegistry.objects.filter(
                pk=int(subdivision_id), country_id=alpha2
            ).first()
        except (TypeError, ValueError):
            return None
    if province_id in (None, ""):
        return None
    try:
        province_id = int(province_id)
    except (TypeError, ValueError):
        return None
    from apps.global_registries.models import Province

    province = Province.objects.select_related("region").filter(pk=province_id).first()
    if not province:
        return None
    alpha2 = canonical_country_alpha2(province.region_id)
    if not alpha2:
        return None
    country = CountryRegistry.objects.filter(code=alpha2).first()
    if not country:
        return None
    subdivision, _created = SubdivisionRegistry.objects.get_or_create(
        country=country,
        code=str(province.code or province.name).upper()[:32],
        defaults={
            "name": province.name,
            "subdivision_type": "province",
            "metadata": {
                "legacy_province_id": province.pk,
                "legacy_region_code": province.region_id,
            },
        },
    )
    return subdivision


def resolve_registry_codes(model, raw_codes: list[str]) -> list:
    codes = [
        str(code or "").strip().upper() for code in raw_codes if str(code or "").strip()
    ]
    if not codes:
        return []
    # unbounded-collection-allow: registry-code-resolve-bounded-by-request-payload
    rows = list(model.objects.filter(code__in=codes, is_active=True))
    rows_by_code = {str(row.code).upper(): row for row in rows}
    return [rows_by_code[code] for code in codes if code in rows_by_code]
