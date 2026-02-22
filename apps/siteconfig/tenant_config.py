"""
Global Powerhouse Phase A: getTenantModules and useLocalSettings.

- getTenantModules(school_id) / get_tenant_modules(school): union of feature keys from
  all systems assigned via TenantSystem, plus SystemFeature rows, plus config.enabled_features.
- useLocalSettings(request) / get_tenant_locale(request): merged locale/config from
  selected systems + School.settings (timezone, locale, currency, date_format, grading_scale).
"""
from __future__ import annotations

import logging
from typing import Any

from django.db.models import QuerySet

logger = logging.getLogger(__name__)


def get_tenant_modules(school) -> list[str]:
    """
    Return deduplicated list of feature/module codes enabled for the tenant.

    (1) Load all system_ids for the school from TenantSystem.
    (2) Load all feature_keys from SystemFeature for those systems.
    (3) Also include enabled_features from each system's config JSON.
    (4) Return sorted unique list.

    Schools with no TenantSystem rows (legacy) are handled by callers that fall back
    to EducationSystemProfile.for_school() and optional backfill.
    """
    if school is None:
        return []
    try:
        from apps.siteconfig.models import TenantSystem, SystemFeature, EducationSystemProfile
    except ImportError:
        return []

    system_ids = list(
        TenantSystem.objects.filter(school=school)
        .values_list("system_id", flat=True)
        .distinct()
    )
    if not system_ids:
        return []

    # From SystemFeature table
    keys_from_table = set(
        SystemFeature.objects.filter(system_id__in=system_ids)
        .values_list("feature_key", flat=True)
        .distinct()
    )
    # Normalize to lowercase for consistency
    keys_from_table = {str(k).strip().lower() for k in keys_from_table if k}

    # From config.enabled_features on each profile
    profiles = EducationSystemProfile.objects.filter(id__in=system_ids).only("config")
    for profile in profiles:
        config = getattr(profile, "config", None) or {}
        if isinstance(config, dict):
            enabled = config.get("enabled_features") or config.get("enabled_modules")
            if isinstance(enabled, list):
                for item in enabled:
                    if isinstance(item, str) and item.strip():
                        keys_from_table.add(item.strip().lower())
                    elif isinstance(item, dict) and item.get("code"):
                        keys_from_table.add(str(item["code"]).strip().lower())

    return sorted(keys_from_table)


def get_tenant_locale(request=None, school=None) -> dict[str, Any]:
    """
    Merge timezone, locale, currency, date_format, grading_scale from:
    (1) All selected systems (EducationSystemProfile.config) for the school,
    (2) School.settings overrides.

    Precedence: school override > first system (by order) > defaults.

    Returns a dict with keys: timezone, locale, currency, date_format, grading_scale,
    and optionally default_language, default_timezone, academic_year_start_month,
    term_count_per_year, term_labels (from merged config).
    """
    out: dict[str, Any] = {
        "timezone": "UTC",
        "locale": "en",
        "currency": "USD",
        "date_format": "DD/MM/YYYY",
        "grading_scale": "0-100",
        "default_language": "en",
        "default_timezone": "UTC",
    }
    if school is None and request is not None:
        school = getattr(request, "school", None)
    if school is None:
        return out

    try:
        from apps.siteconfig.models import TenantSystem, EducationSystemProfile
    except ImportError:
        pass
    else:
        system_ids = list(
            TenantSystem.objects.filter(school=school)
            .order_by("system__name")
            .values_list("system_id", flat=True)
            .distinct()
        )
        for pid in system_ids:
            profile = EducationSystemProfile.objects.filter(id=pid).first()
            if not profile:
                continue
            # First system wins for unset keys
            if not out.get("default_timezone") or out.get("default_timezone") == "UTC":
                out["default_timezone"] = getattr(profile, "default_timezone", None) or "UTC"
            if not out.get("default_language"):
                out["default_language"] = getattr(profile, "default_language", None) or "en"
            if not out.get("currency") or out.get("currency") == "USD":
                out["currency"] = getattr(profile, "default_currency", None) or "USD"
            if not out.get("grading_scale"):
                out["grading_scale"] = getattr(profile, "grading_scale", None) or "0-100"
            config = getattr(profile, "config", None) or {}
            if isinstance(config, dict):
                if config.get("date_format") and not out.get("date_format"):
                    out["date_format"] = config["date_format"]
                if config.get("timezone"):
                    out["default_timezone"] = config["timezone"]
            out["timezone"] = out.get("default_timezone") or out["timezone"]
            out["locale"] = out.get("default_language") or out["locale"]
            break

    # School-level overrides
    settings = getattr(school, "settings", None) or {}
    if isinstance(settings, dict):
        if settings.get("timezone"):
            out["timezone"] = settings["timezone"]
        if settings.get("default_language") or settings.get("locale"):
            out["locale"] = settings.get("default_language") or settings.get("locale", "en")
        if settings.get("default_currency") or settings.get("currency"):
            out["currency"] = settings.get("default_currency") or settings.get("currency", "USD")
        if settings.get("date_format"):
            out["date_format"] = settings["date_format"]
        if settings.get("grading_scale"):
            out["grading_scale"] = settings["grading_scale"]
        edu = settings.get("education_profile") or {}
        if isinstance(edu, dict) and edu.get("default_timezone"):
            out["timezone"] = edu["default_timezone"]

    # School model fields override
    if getattr(school, "timezone", None):
        out["timezone"] = school.timezone
    if getattr(school, "default_region_id", None):
        try:
            from apps.siteconfig.models import RegionConfig
            region = RegionConfig.objects.filter(pk=school.default_region_id).first()
            if region:
                if not out.get("currency") or out.get("currency") == "USD":
                    out["currency"] = getattr(region, "default_currency", None) or out["currency"]
                if not out.get("date_format"):
                    out["date_format"] = getattr(region, "date_format", None) or out["date_format"]
                if not out.get("grading_scale"):
                    out["grading_scale"] = getattr(region, "grading_scale", None) or out["grading_scale"]
        except Exception:
            pass

    out["default_timezone"] = out.get("timezone") or out.get("default_timezone") or "UTC"
    out["default_language"] = out.get("locale") or out.get("default_language") or "en"
    return out


def use_local_settings(request=None, school=None) -> dict[str, Any]:
    """Alias for get_tenant_locale for plan compatibility."""
    return get_tenant_locale(request=request, school=school)


def get_custom_field_definitions(school, entity: str = "students") -> list[dict[str, Any]]:
    """
    Phase C: Return custom field definitions for Student or Staff from School.settings.
    entity is 'students' or 'staff'. Returns list of dicts with key, label, type (e.g. text, number).
    """
    if not school:
        return []
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return []
    defs = settings.get("custom_field_definitions") or {}
    return defs.get(entity) if isinstance(defs.get(entity), list) else []


def get_report_template_family_for_school(school) -> str:
    """
    Phase C: Return report_template_family for the tenant from EducationSystemProfile.config.
    Used to filter ReportTemplate listing and select layout (e.g. French Lycée vs UK standard).
    Returns "" when school is None or no config.
    """
    if school is None:
        return ""
    try:
        from apps.siteconfig.models import TenantSystem, EducationSystemProfile
        system_ids = list(
            TenantSystem.objects.filter(school=school)
            .order_by("system__name")
            .values_list("system_id", flat=True)
            .distinct()[:1]
        )
        if system_ids:
            profile = EducationSystemProfile.objects.filter(id=system_ids[0]).first()
            if profile and isinstance(getattr(profile, "config", None), dict):
                return (profile.config.get("report_template_family") or profile.config.get("report_template") or "").strip()
    except Exception:
        pass
    return ""


def get_grading_schema_for_school(school) -> dict[str, Any]:
    """
    Phase C: Return grading schema (scale id and optional bands) for the tenant from
    get_tenant_locale + EducationSystemProfile.config. Use in grading/reports (Strategy Pattern).
    Returns dict with keys: scale (e.g. '0-20', '0-100'), and optionally grade_bands, pass_mark from config.
    """
    if school is None:
        return {"scale": "0-100", "grade_bands": None, "pass_mark": None}
    locale = get_tenant_locale(school=school)
    scale = (locale.get("grading_scale") or "0-100").strip()
    out = {"scale": scale, "grade_bands": None, "pass_mark": None}
    try:
        from apps.siteconfig.models import TenantSystem, EducationSystemProfile
        system_ids = list(
            TenantSystem.objects.filter(school=school)
            .order_by("system__name")
            .values_list("system_id", flat=True)
            .distinct()[:1]
        )
        if system_ids:
            profile = EducationSystemProfile.objects.filter(id=system_ids[0]).first()
            if profile and isinstance(getattr(profile, "config", None), dict):
                cfg = profile.config
                out["grade_bands"] = cfg.get("grade_bands") or cfg.get("letter_bands")
                out["pass_mark"] = cfg.get("pass_mark") or cfg.get("pass_threshold")
    except Exception:
        pass
    return out


def get_custom_field_definitions_for_school(school, entity_type: str) -> list[dict]:
    """
    Phase C: Return custom field definitions for students or staff from School.settings.
    entity_type is 'students' or 'staff'. Each item: {"key": str, "label": str, "type": "text"|"number"|"date"}.
    """
    if school is None or entity_type not in ("students", "staff"):
        return []
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        return []
    defs = settings.get("custom_field_definitions") or {}
    if not isinstance(defs, dict):
        return []
    items = defs.get(entity_type)
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict) and x.get("key")]


def format_date_tenant(dt, request=None, school=None) -> str:
    """
    Phase C: Format date using tenant locale (date_format from get_tenant_locale).
    No hardcoded DD/MM/YYYY; use in views/templates when request or school is available.
    """
    if dt is None:
        return ""
    locale = get_tenant_locale(request=request, school=school)
    pattern = (locale.get("date_format") or "DD/MM/YYYY").strip()
    from django.utils import dateformat
    fmt = pattern.replace("YYYY", "Y").replace("DD", "d").replace("MM", "m")
    try:
        return dateformat.format(dt, fmt)
    except Exception:
        return str(dt)


def format_currency_tenant(amount, request=None, school=None) -> str:
    """
    Phase C: Format amount as currency using tenant locale (currency from get_tenant_locale).
    No hardcoded $ or XAF; uses get_currency_symbol(currency) and tenant separators.
    """
    try:
        amt = float(amount)
    except (TypeError, ValueError):
        return str(amount)
    locale = get_tenant_locale(request=request, school=school)
    currency = (locale.get("currency") or locale.get("default_currency") or "USD").strip()
    from apps.siteconfig.currency import get_currency_symbol
    symbol = get_currency_symbol(currency)
    dec_sep = locale.get("decimal_separator") or "."
    thousands_sep = locale.get("thousands_separator") or ","
    s = f"{amt:,.2f}".replace(",", "\x01").replace(".", dec_sep).replace("\x01", thousands_sep)
    return f"{symbol}{s}" if symbol else s


def sync_tenant_modules_to_school_features(school, *, persist: bool = True) -> dict[str, bool]:
    """
    Optional Phase A: sync get_tenant_modules(school) result into School.features
    so existing has_feature() works without changing every call site.

    If persist=True, updates school.features with {code: True for code in modules}.
    Returns the dict that was (or would be) written to School.features.
    """
    modules = get_tenant_modules(school)
    if not school:
        return {}
    features = {code: True for code in modules}
    if persist:
        current = dict(getattr(school, "features", None) or {})
        # Merge: keep existing keys, set module keys from get_tenant_modules
        for k, v in features.items():
            current[k] = v
        school.features = current
        school.save(update_fields=["features", "updated_at"])
    return features
