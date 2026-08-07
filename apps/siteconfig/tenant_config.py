"""
Global Powerhouse Phase A: getTenantModules and useLocalSettings.

- getTenantModules(school_id) / get_tenant_modules(school): union of feature keys from
  all systems assigned via TenantSystem, plus SystemFeature rows, plus config.enabled_features.
- useLocalSettings(request) / get_tenant_locale(request): merged locale/config from
  selected systems + School.settings (timezone, locale, currency, date_format, grading_scale).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from django.core.exceptions import ObjectDoesNotExist
from django.db.utils import DatabaseError

logger = logging.getLogger(__name__)
SOFT_TENANT_CONFIG_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    ObjectDoesNotExist,
    RuntimeError,
    TypeError,
    ValueError,
)


def get_tenant_modules(school) -> list[str]:
    """
    Return deduplicated list of feature/module codes enabled for the tenant.
    Single source: (1) manifest required_apps for school.school_type (merged with inherits),
    (2) union with TenantSystem + SystemFeature + config.enabled_features.

    Schools with no TenantSystem rows (legacy) still get manifest required_apps when school_type is set.
    """
    if school is None:
        return []
    keys = set()

    # (1) Module manifest: required_apps for school_type (World Engine E.2)
    try:
        from apps.siteconfig.module_manifest import get_school_type_config

        school_type = getattr(school, "school_type", None) or "BASE_SCHOOL"
        cfg = get_school_type_config(school_type)
        for app in cfg.get("required_apps") or []:
            if app and isinstance(app, str):
                keys.add(app.strip().lower())
    except SOFT_TENANT_CONFIG_ERRORS:
        pass

    try:
        from apps.siteconfig.models import (
            TenantSystem,
            SystemFeature,
            EducationSystemProfile,
        )
    except ImportError:
        return sorted(keys)

    system_ids = list(
        TenantSystem.objects.filter(school=school)
        .values_list("system_id", flat=True)
        .distinct()
    )
    if not system_ids:
        return sorted(keys)

    # From SystemFeature table
    keys_from_table = set(
        SystemFeature.objects.filter(system_id__in=system_ids)
        .values_list("feature_key", flat=True)
        .distinct()
    )
    keys |= {str(k).strip().lower() for k in keys_from_table if k}

    # From config.enabled_features on each profile
    profiles = EducationSystemProfile.objects.filter(id__in=system_ids).only("config")
    for profile in profiles:
        config = getattr(profile, "config", None) or {}
        if isinstance(config, dict):
            enabled = config.get("enabled_features") or config.get("enabled_modules")
            if isinstance(enabled, list):
                for item in enabled:
                    if isinstance(item, str) and item.strip():
                        keys.add(item.strip().lower())
                    elif isinstance(item, dict) and item.get("code"):
                        keys.add(str(item["code"]).strip().lower())

    return sorted(keys)


def get_compliance_region(school) -> str | None:
    """
    Return Compliance Region for tenant: EU (GDPR), US (FERPA), NDPR (Nigeria), or None.
    Used to auto-enable data masking, retention, and consent flows per region (Universal Education OS XXI).
    """
    if not school:
        return None
    settings = getattr(school, "settings", None) or {}
    if isinstance(settings, dict) and settings.get("compliance_region"):
        return str(settings["compliance_region"]).upper()[:10]
    try:
        from apps.siteconfig.models import RegionConfig

        region = (
            getattr(school, "default_region_id", None)
            and RegionConfig.objects.filter(pk=school.default_region_id).first()
        )
        if region and getattr(region, "code", None):
            code = (region.code or "").upper()
            if code in ("DE", "FR", "IT", "ES", "NL", "BE", "AT", "PL", "EU"):
                return "EU"
            if code == "US":
                return "US"
            if code == "NG":
                return "NDPR"
    except SOFT_TENANT_CONFIG_ERRORS:
        pass
    return None


def get_tenant_enum_choices(school, key: str) -> list[tuple[str, str]]:
    """
    Return tenant-configurable choices for key enums (W3-1).

    Keys: relationship_choices, student_status_choices, dashboard_view_choices.
    School.settings[key] may be a list of [value, label] or [{"value": v, "label": l}].
    If missing or invalid, returns the default model choices.
    """
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    raw = settings.get(key)
    if isinstance(raw, list) and raw:
        out = []
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict) and item.get("value") is not None:
                out.append((str(item["value"]), str(item.get("label", item["value"]))))
            elif isinstance(item, str):
                out.append((item, item))
        if out:
            return out
    # Defaults from models
    if key == "relationship_choices":
        from apps.portal.models import PendingGuardianInvite

        return list(PendingGuardianInvite.Relationship.choices)
    if key == "student_status_choices":
        from apps.people.models import StudentProfile

        return list(StudentProfile.Status.choices)
    if key == "dashboard_view_choices":
        from apps.people.models import TeacherProfile

        return list(TeacherProfile.DashboardView.choices)
    return []


def get_tenant_validation_rules(school) -> dict[str, Any]:
    """
    Return validation & rules from School.settings (W3-2).

    Keys: admission_pattern (regex), file_max_size_mb, allowed_file_types (list),
    phone_regex, refund_reasons (list or free text).
    """
    settings = getattr(school, "settings", None) or {}
    if not isinstance(settings, dict):
        settings = {}
    return {
        "admission_pattern": settings.get("admission_pattern") or r"^[A-Z0-9\-]+$",
        "file_max_size_mb": settings.get("file_max_size_mb", 10),
        "allowed_file_types": settings.get("allowed_file_types")
        or ["pdf", "jpg", "jpeg", "png"],
        "phone_regex": settings.get("phone_regex") or r"^\+?[\d\s\-()]{8,20}$",
        "refund_reasons": settings.get("refund_reasons") or [],
    }


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
        "labels_map": {},
        "is_rtl": False,
        "calendar_system": "gregorian",
        "week_start_day": 0,
        "offline_mode_default": False,
        "low_bandwidth": False,
    }
    if school is None and request is not None:
        school = getattr(request, "school", None)
    if school is None:
        return out

    # Country-level brand defaults (GlobalBrandRegistry) before system/profile overlays.
    try:
        from apps.siteconfig.brand_registry import resolve_global_brand_context

        brand_context = resolve_global_brand_context(school=school)
        out["locale"] = brand_context.get("primary_language") or out["locale"]
        out["default_language"] = (
            brand_context.get("primary_language") or out["default_language"]
        )
        out["currency"] = brand_context.get("currency_code") or out["currency"]
        out["labels_map"] = brand_context.get("labels_map") or {}
        ui_cfg = brand_context.get("ui_config") or {}
        if isinstance(ui_cfg, dict):
            out["date_format"] = ui_cfg.get("date_format") or out["date_format"]
            out["is_rtl"] = bool(ui_cfg.get("is_rtl", False))
            if ui_cfg.get("timezone"):
                out["timezone"] = ui_cfg["timezone"]
                out["default_timezone"] = ui_cfg["timezone"]
    except SOFT_TENANT_CONFIG_ERRORS:
        pass

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
                out["default_timezone"] = (
                    getattr(profile, "default_timezone", None) or "UTC"
                )
            if not out.get("default_language"):
                out["default_language"] = (
                    getattr(profile, "default_language", None) or "en"
                )
            if not out.get("currency") or out.get("currency") == "USD":
                out["currency"] = getattr(profile, "default_currency", None) or "USD"
            if not out.get("grading_scale"):
                out["grading_scale"] = (
                    getattr(profile, "grading_scale", None) or "0-100"
                )
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
            out["locale"] = settings.get("default_language") or settings.get(
                "locale", "en"
            )
        if settings.get("default_currency") or settings.get("currency"):
            out["currency"] = settings.get("default_currency") or settings.get(
                "currency", "USD"
            )
        if settings.get("date_format"):
            out["date_format"] = settings["date_format"]
        if settings.get("grading_scale"):
            out["grading_scale"] = settings["grading_scale"]
        if settings.get("calendar_system"):
            out["calendar_system"] = str(settings["calendar_system"]).strip().lower()
        if settings.get("week_start_day") is not None:
            out["week_start_day"] = int(settings["week_start_day"]) % 7
        if isinstance(settings.get("labels_map"), dict):
            out["labels_map"] = {
                **(out.get("labels_map") or {}),
                **settings["labels_map"],
            }
        edu = settings.get("education_profile") or {}
        if isinstance(edu, dict) and edu.get("default_timezone"):
            out["timezone"] = edu["default_timezone"]
        if isinstance(edu, dict) and isinstance(edu.get("labels_map"), dict):
            out["labels_map"] = {**(out.get("labels_map") or {}), **edu["labels_map"]}
        if settings.get("rtl") is True:
            out["is_rtl"] = True

    # School model fields override
    if getattr(school, "timezone", None):
        out["timezone"] = school.timezone
    if getattr(school, "default_region_id", None):
        try:
            from apps.siteconfig.models import RegionConfig

            region = RegionConfig.objects.filter(pk=school.default_region_id).first()
            if region:
                if not out.get("currency") or out.get("currency") == "USD":
                    out["currency"] = (
                        getattr(region, "default_currency", None) or out["currency"]
                    )
                if not out.get("date_format"):
                    out["date_format"] = (
                        getattr(region, "date_format", None) or out["date_format"]
                    )
                if not out.get("grading_scale"):
                    out["grading_scale"] = (
                        getattr(region, "grading_scale", None) or out["grading_scale"]
                    )
                cal = getattr(region, "calendar_system", None)
                if cal:
                    out["calendar_system"] = str(cal).strip().lower()
                wsd = getattr(region, "week_start_day", None)
                if wsd is not None:
                    out["week_start_day"] = int(wsd) % 7
                pack = get_regional_policy_pack(str(getattr(region, "code", "") or ""))
                if isinstance(pack, dict):
                    defaults = pack.get("defaults") or {}
                    if defaults.get("offline_mode_default") is True:
                        out["offline_mode_default"] = True
                        out["low_bandwidth"] = True
        except SOFT_TENANT_CONFIG_ERRORS:
            pass

    out["default_timezone"] = (
        out.get("timezone") or out.get("default_timezone") or "UTC"
    )
    out["default_language"] = out.get("locale") or out.get("default_language") or "en"
    return out


def use_local_settings(request=None, school=None) -> dict[str, Any]:
    """Alias for get_tenant_locale for plan compatibility."""
    return get_tenant_locale(request=request, school=school)


def get_custom_field_definitions(
    school, entity: str = "students"
) -> list[dict[str, Any]]:
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
                return (
                    profile.config.get("report_template_family")
                    or profile.config.get("report_template")
                    or ""
                ).strip()
    except SOFT_TENANT_CONFIG_ERRORS:
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
    except SOFT_TENANT_CONFIG_ERRORS:
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
    from apps.platform_runtime.localization import format_school_date

    return format_school_date(dt, date_format=pattern)


def format_currency_tenant(amount, request=None, school=None) -> str:
    """
    Phase C: Format amount as currency using tenant locale (currency from get_tenant_locale).

    Routes through ``apps.registries.currency.format_money`` so the amount honours
    the currency's minor-unit digit count and symbol placement (XAF -> "50 000 FCFA",
    not "FCFA50,000.00"), while still respecting any locale-configured separators.
    """
    if amount is None:
        return ""
    try:
        float(amount)
    except (TypeError, ValueError):
        return str(amount)
    locale = get_tenant_locale(request=request, school=school)
    currency = (
        locale.get("currency") or locale.get("default_currency") or "USD"
    ).strip()
    from apps.registries.currency import format_money

    return format_money(
        amount,
        currency,
        decimal_sep=locale.get("decimal_separator"),
        thousands_sep=locale.get("thousands_separator"),
    )


def sync_tenant_modules_to_school_features(
    school, *, persist: bool = True
) -> dict[str, bool]:
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
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except SOFT_TENANT_CONFIG_ERRORS:
            pass
    return features


# -----------------------------------------------------------------------------
# Titan Config Compiler (CFG-101/CFG-102/CFG-103 baseline)
# -----------------------------------------------------------------------------

# Regional policy packs are versioned artifacts with default settings + lock metadata.
# Non-locked keys remain tenant-configurable in school.settings.
REGIONAL_POLICY_PACKS: dict[str, dict[str, Any]] = {
    "US": {
        "code": "US",
        "version": "2026.1",
        "name": "United States Education Pack",
        "defaults": {
            "privacy_framework": "FERPA_COPPA",
            "data_residency_region": "us-east-1",
            "default_language": "en",
            "currency": "USD",
            "date_format": "MM/DD/YYYY",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "guardian_opt_in",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "EU": {
        "code": "EU",
        "version": "2026.1",
        "name": "European Union Education Pack",
        "defaults": {
            "privacy_framework": "GDPR",
            "data_residency_region": "eu-central-1",
            "default_language": "en",
            "currency": "EUR",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-20",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "consent_mode": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "BRA": {
        "code": "BRA",
        "version": "2026.1",
        "name": "Brazil LGPD Pack",
        "defaults": {
            "privacy_framework": "LGPD",
            "data_residency_region": "sa-east-1",
            "default_language": "pt",
            "currency": "BRL",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "LCA": {
        "code": "LCA",
        "version": "2026.1",
        "name": "Low-Connectivity Africa Pack",
        "defaults": {
            "privacy_framework": "regional_default",
            "data_residency_region": "af-south-1",
            "default_language": "en",
            "currency": "XAF",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-20",
            "offline_mode_default": True,
            "offline_sync_strategy": "background_retry",
            "mobile_money_default": True,
        },
        "locks": {
            "offline_mode_default": {
                "compliance_locked": False,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "WAEC": {
        "code": "WAEC",
        "version": "2026.1",
        "name": "West Africa (WAEC / Anglophone) Pack",
        "defaults": {
            "privacy_framework": "regional_default",
            "data_residency_region": "af-west-1",
            "default_language": "en",
            "currency": "NGN",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "term_preset": "WAEC",
            "offline_mode_default": False,
            "consent_mode": "standard",
        },
        "locks": {},
    },
    "AFR_FR": {
        "code": "AFR_FR",
        "version": "2026.1",
        "name": "Francophone Africa Pack",
        "defaults": {
            "privacy_framework": "regional_default",
            "data_residency_region": "af-west-1",
            "default_language": "fr",
            "currency": "XAF",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-20",
            "offline_mode_default": False,
            "consent_mode": "standard",
        },
        "locks": {},
    },
    "GBR": {
        "code": "GBR",
        "version": "2026.1",
        "name": "UK / British Education Pack",
        "defaults": {
            "privacy_framework": "GDPR",
            "data_residency_region": "eu-west-2",
            "default_language": "en",
            "currency": "GBP",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "A*-G",
            "term_preset": "UK",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "AUS": {
        "code": "AUS",
        "version": "2026.1",
        "name": "Australia Education Pack",
        "defaults": {
            "privacy_framework": "APPA",
            "data_residency_region": "ap-southeast-2",
            "default_language": "en",
            "currency": "AUD",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "term_preset": "AU",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "NZL": {
        "code": "NZL",
        "version": "2026.1",
        "name": "New Zealand Education Pack",
        "defaults": {
            "privacy_framework": "PRIVACY_ACT_NZ",
            "data_residency_region": "ap-southeast-2",
            "default_language": "en",
            "currency": "NZD",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "term_preset": "NZ",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "ASIA": {
        "code": "ASIA",
        "version": "2026.1",
        "name": "Asia Education Pack",
        "defaults": {
            "privacy_framework": "regional_default",
            "data_residency_region": "ap-southeast-1",
            "default_language": "en",
            "currency": "USD",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "standard",
        },
        "locks": {},
    },
    "POPIA": {
        "code": "POPIA",
        "version": "2026.1",
        "name": "South Africa POPIA Education Pack",
        "defaults": {
            "privacy_framework": "POPIA",
            "data_residency_region": "af-south-1",
            "default_language": "en",
            "currency": "ZAR",
            "date_format": "YYYY/MM/DD",
            "grading_scale": "0-100",
            "offline_mode_default": True,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "PIPL": {
        "code": "PIPL",
        "version": "2026.1",
        "name": "China PIPL Education Pack",
        "defaults": {
            "privacy_framework": "PIPL",
            "data_residency_region": "cn-north-1",
            "default_language": "zh",
            "currency": "CNY",
            "date_format": "YYYY-MM-DD",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "CAN": {
        "code": "CAN",
        "version": "2026.1",
        "name": "Canada Education Pack",
        "defaults": {
            "privacy_framework": "PIPEDA",
            "data_residency_region": "ca-central-1",
            "default_language": "en",
            "currency": "CAD",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "guardian_opt_in",
        },
        "locks": {
            "privacy_framework": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
            "data_residency_region": {
                "compliance_locked": True,
                "tenant_editable": False,
                "requires_approval": True,
            },
        },
    },
    "LATAM_ES": {
        "code": "LATAM_ES",
        "version": "2026.1",
        "name": "Spanish South America Pack",
        "defaults": {
            "privacy_framework": "regional_default",
            "data_residency_region": "sa-east-1",
            "default_language": "es",
            "currency": "USD",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "explicit_consent",
        },
        "locks": {},
    },
    "MENA": {
        "code": "MENA",
        "version": "2026.1",
        "name": "Middle East & North Africa Pack",
        "defaults": {
            "privacy_framework": "regional_default",
            "data_residency_region": "me-south-1",
            "default_language": "ar",
            "currency": "USD",
            "date_format": "DD/MM/YYYY",
            "grading_scale": "0-100",
            "offline_mode_default": False,
            "consent_mode": "standard",
            "rtl": True,
        },
        "locks": {},
    },
}

# Internal keys used to store compiled config metadata in School.settings.
# These keys must not be treated as tenant-authored overrides.
INTERNAL_TENANT_SETTINGS_KEYS = {
    "tenant_compiled_config",
    "tenant_config_metadata",
    "tenant_config_layers",
    "tenant_policy_pack",
    "tenant_config_compiled_at",
}


def _global_config_defaults() -> dict[str, Any]:
    return {
        "privacy_framework": "regional_default",
        "data_residency_region": "global",
        "default_language": "en",
        "currency": "USD",
        "date_format": "DD/MM/YYYY",
        "grading_scale": "0-100",
        "offline_mode_default": False,
        "consent_mode": "standard",
        "feature_modules": [],
    }


def get_regional_policy_pack(region_code: str | None) -> dict[str, Any]:
    """
    Resolve policy pack by region code.
    Known aliases:
    - USA -> US; CAN/CA -> CAN
    - GBR; FRA/DEU/ESP/ITA/... -> EU
    - BRA; ARG/COL/CHL/PER/... -> LATAM_ES
    - WAEC (Anglophone West Africa): NGA, GHA, GMB, SLE, LBR
    - AFR_FR (Francophone Africa): CMR, SEN, CIV, BEN, TGO, BFA, MLI, NER
    - LCA (Africa low-connectivity): UGA, KEN, RWA, ETH, TZA, ZAF
    - ASIA: IND, SGP, CHN, JPN, KOR, MYS, THA, IDN, PHL, VNM
    - MENA: ARE, SAU, EGY, JOR, LBN, KWT, BHR, QAT, OMN
    """
    code = (region_code or "").strip().upper()
    if not code:
        return {}
    if code in REGIONAL_POLICY_PACKS:
        return deepcopy(REGIONAL_POLICY_PACKS[code])
    if code in {"USA", "US"}:
        return deepcopy(REGIONAL_POLICY_PACKS["US"])
    if code in {"CAN", "CA"}:
        return deepcopy(REGIONAL_POLICY_PACKS["CAN"])
    if code == "GBR":
        return deepcopy(REGIONAL_POLICY_PACKS["GBR"])
    if code in {
        "EU",
        "FRA",
        "DEU",
        "ESP",
        "ITA",
        "NLD",
        "BEL",
        "SWE",
        "DNK",
        "FIN",
        "NOR",
        "IRL",
        "AUT",
        "PRT",
        "GRC",
        "POL",
        "CZE",
        "ROU",
        "HUN",
    }:
        return deepcopy(REGIONAL_POLICY_PACKS["EU"])
    if code == "BRA":
        return deepcopy(REGIONAL_POLICY_PACKS["BRA"])
    if code in {"NGA", "GHA", "GMB", "SLE", "LBR"}:
        return deepcopy(REGIONAL_POLICY_PACKS["WAEC"])
    if code in {"CMR", "SEN", "CIV", "BEN", "TGO", "BFA", "MLI", "NER", "TCD", "CAF"}:
        return deepcopy(REGIONAL_POLICY_PACKS["AFR_FR"])
    if code == "ZAF":
        return deepcopy(REGIONAL_POLICY_PACKS["POPIA"])
    if code in {
        "UGA",
        "KEN",
        "RWA",
        "ETH",
        "TZA",
        "ZWE",
        "ZMB",
        "MWI",
        "MOZ",
        "AGO",
        "SDN",
    }:
        return deepcopy(REGIONAL_POLICY_PACKS["LCA"])
    if code in {"CHN", "CN"}:
        return deepcopy(REGIONAL_POLICY_PACKS["PIPL"])
    if code in {
        "IND",
        "SGP",
        "JPN",
        "KOR",
        "MYS",
        "THA",
        "IDN",
        "PHL",
        "VNM",
        "PAK",
        "BGD",
        "LKA",
        "NPL",
        "MMR",
        "KHM",
        "LAO",
    }:
        return deepcopy(REGIONAL_POLICY_PACKS["ASIA"])
    if code in {"ARG", "COL", "CHL", "PER", "ECU", "BOL", "PRY", "URY", "VEN"}:
        return deepcopy(REGIONAL_POLICY_PACKS["LATAM_ES"])
    if code in {
        "ARE",
        "SAU",
        "EGY",
        "JOR",
        "LBN",
        "KWT",
        "BHR",
        "QAT",
        "OMN",
        "IRQ",
        "IRN",
        "SYR",
        "YEM",
        "PSE",
        "DZA",
        "TUN",
        "MAR",
        "LBY",
    }:
        return deepcopy(REGIONAL_POLICY_PACKS["MENA"])
    if code in {"AUS", "AU"}:
        return deepcopy(REGIONAL_POLICY_PACKS["AUS"])
    if code in {"NZL", "NZ"}:
        return deepcopy(REGIONAL_POLICY_PACKS["NZL"])
    return {}


def compile_effective_tenant_config(
    school,
    *,
    campus_overrides: dict[str, Any] | None = None,
    user_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compile effective tenant configuration using deterministic precedence:
    1. global defaults
    2. regional policy pack
    3. education profile defaults/config
    4. plan/add-on derived features
    5. tenant overrides (school.settings)
    6. campus overrides
    7. user overrides

    Returns:
      {
        "effective": {...},
        "metadata": {
            "<key>": {
                "source": "...",
                "auto_applied": bool,
                "tenant_editable": bool,
                "compliance_locked": bool,
                "requires_approval": bool
            }
        },
        "pack": {"code": "...", "version": "..."} | {},
        "layers": ["global", "..."],
      }
    """
    if school is None:
        return {"effective": {}, "metadata": {}, "pack": {}, "layers": []}

    effective = _global_config_defaults()
    metadata: dict[str, dict[str, Any]] = {}
    layers = ["global"]

    def apply_layer(
        values: dict[str, Any],
        source: str,
        *,
        auto_applied: bool,
        default_editable: bool = True,
    ):
        if not isinstance(values, dict):
            return
        for key, value in values.items():
            effective[key] = deepcopy(value)
            current = metadata.get(key, {})
            metadata[key] = {
                "source": source,
                "auto_applied": bool(auto_applied),
                "tenant_editable": bool(
                    current.get("tenant_editable", default_editable)
                ),
                "compliance_locked": bool(current.get("compliance_locked", False)),
                "requires_approval": bool(current.get("requires_approval", False)),
            }

    # Layer 2: regional policy pack
    region_code = getattr(
        getattr(school, "default_region", None), "code", None
    ) or getattr(school, "default_region_id", None)
    pack = get_regional_policy_pack(region_code)
    if pack:
        apply_layer(
            pack.get("defaults") or {},
            f"region_pack:{pack.get('code')}",
            auto_applied=True,
            default_editable=True,
        )
        for key, lock in (pack.get("locks") or {}).items():
            if key not in metadata:
                metadata[key] = {
                    "source": f"region_pack:{pack.get('code')}",
                    "auto_applied": True,
                    "tenant_editable": True,
                    "compliance_locked": False,
                    "requires_approval": False,
                }
            if isinstance(lock, dict):
                metadata[key]["tenant_editable"] = bool(
                    lock.get("tenant_editable", metadata[key]["tenant_editable"])
                )
                metadata[key]["compliance_locked"] = bool(
                    lock.get("compliance_locked", False)
                )
                metadata[key]["requires_approval"] = bool(
                    lock.get("requires_approval", False)
                )
        layers.append("region_pack")

    # Layer 3: education profile (if available)
    try:
        from apps.siteconfig.education_profile_engine import resolve_profile_for_school

        profile = resolve_profile_for_school(school, auto_create=True)
    except SOFT_TENANT_CONFIG_ERRORS:
        profile = None
    if profile:
        profile_values = {
            "default_language": getattr(profile, "default_language", "")
            or effective.get("default_language"),
            "currency": getattr(profile, "default_currency", "")
            or effective.get("currency"),
            "grading_scale": getattr(profile, "grading_scale", "")
            or effective.get("grading_scale"),
            "date_format": (getattr(profile, "config", {}) or {}).get("date_format")
            or effective.get("date_format"),
            "education_profile_code": getattr(profile, "code", ""),
            "education_profile_version": getattr(profile, "version", ""),
            "term_labels": profile.normalized_term_labels()
            if hasattr(profile, "normalized_term_labels")
            else [],
        }
        apply_layer(
            profile_values,
            "education_profile",
            auto_applied=True,
            default_editable=True,
        )
        if isinstance(getattr(profile, "config", None), dict):
            apply_layer(
                profile.config,
                "education_profile_config",
                auto_applied=True,
                default_editable=True,
            )
        layers.append("education_profile")

    # Layer 4: plan/add-ons to feature_modules
    modules = []
    plan = getattr(school, "plan", None)
    if plan and isinstance(getattr(plan, "included_features", None), list):
        modules.extend(
            [str(x).strip().lower() for x in plan.included_features if str(x).strip()]
        )
    addons = getattr(school, "addons", None) or []
    if isinstance(addons, list):
        modules.extend([str(x).strip().lower() for x in addons if str(x).strip()])
    tenant_modules = get_tenant_modules(school)
    modules.extend([str(x).strip().lower() for x in tenant_modules if str(x).strip()])
    if modules:
        uniq_modules = sorted(set(modules))
        apply_layer(
            {"feature_modules": uniq_modules},
            "plan_addons",
            auto_applied=True,
            default_editable=True,
        )
        layers.append("plan_addons")

    # Layer 5: tenant overrides
    tenant_overrides = getattr(school, "settings", None) or {}
    if isinstance(tenant_overrides, dict):
        filtered_tenant_overrides = {
            key: value
            for key, value in tenant_overrides.items()
            if key not in INTERNAL_TENANT_SETTINGS_KEYS
        }
        apply_layer(
            filtered_tenant_overrides,
            "tenant_override",
            auto_applied=False,
            default_editable=True,
        )
        layers.append("tenant_override")

    # Layer 6: campus overrides
    if isinstance(campus_overrides, dict) and campus_overrides:
        apply_layer(
            campus_overrides,
            "campus_override",
            auto_applied=False,
            default_editable=True,
        )
        layers.append("campus_override")

    # Layer 7: user overrides
    if isinstance(user_overrides, dict) and user_overrides:
        apply_layer(
            user_overrides, "user_override", auto_applied=False, default_editable=True
        )
        layers.append("user_override")

    # Fill metadata defaults for keys without explicit lock metadata.
    for key in effective.keys():
        if key not in metadata:
            metadata[key] = {
                "source": "global",
                "auto_applied": key in _global_config_defaults(),
                "tenant_editable": True,
                "compliance_locked": False,
                "requires_approval": False,
            }

    return {
        "effective": effective,
        "metadata": metadata,
        "pack": {"code": pack.get("code"), "version": pack.get("version")}
        if pack
        else {},
        "layers": layers,
    }


def is_tenant_setting_editable(compiled: dict[str, Any], key: str) -> bool:
    """Helper for governance flows: can tenant edit this key directly?"""
    info = (compiled.get("metadata") or {}).get(key) or {}
    return bool(info.get("tenant_editable", True)) and not bool(
        info.get("compliance_locked", False)
    )


def persist_compiled_tenant_config(
    school,
    *,
    campus_overrides: dict[str, Any] | None = None,
    user_overrides: dict[str, Any] | None = None,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Compile and optionally persist tenant config snapshot into School.settings.

    Stored keys:
    - tenant_compiled_config
    - tenant_config_metadata
    - tenant_config_layers
    - tenant_policy_pack
    - tenant_config_compiled_at
    """
    compiled = compile_effective_tenant_config(
        school,
        campus_overrides=campus_overrides,
        user_overrides=user_overrides,
    )
    if not school or not persist:
        return compiled

    from django.utils import timezone

    settings = dict(getattr(school, "settings", None) or {})
    settings["tenant_compiled_config"] = compiled.get("effective") or {}
    settings["tenant_config_metadata"] = compiled.get("metadata") or {}
    settings["tenant_config_layers"] = compiled.get("layers") or []
    settings["tenant_policy_pack"] = compiled.get("pack") or {}
    settings["tenant_config_compiled_at"] = timezone.now().isoformat()

    school.settings = settings
    school.save(update_fields=["settings", "updated_at"])
    try:
        from apps.policies.policy_registry import invalidate_policy_cache

        invalidate_policy_cache(school)
    except SOFT_TENANT_CONFIG_ERRORS:
        pass
    return compiled


def apply_tenant_settings_overrides(
    school,
    overrides: dict[str, Any] | None,
    *,
    actor_is_superadmin: bool = False,
    force_override: bool = False,
    persist: bool = True,
) -> dict[str, Any]:
    """
    Apply tenant overrides with policy metadata enforcement.

    Behavior:
    - `compliance_locked=True` keys are blocked unless superadmin force override.
    - `tenant_editable=False` keys are blocked unless superadmin force override.
    - `requires_approval=True` keys are reported separately when blocked.
    """
    payload = overrides if isinstance(overrides, dict) else {}
    if not school:
        return {
            "applied": {},
            "blocked": {},
            "requires_approval": {},
            "saved": False,
        }

    compiled = compile_effective_tenant_config(school)
    metadata = compiled.get("metadata") or {}

    blocked: dict[str, str] = {}
    requires_approval: dict[str, str] = {}
    applied: dict[str, Any] = {}

    for key, value in payload.items():
        if key in INTERNAL_TENANT_SETTINGS_KEYS:
            blocked[key] = "internal_key_not_editable"
            continue
        info = metadata.get(key) or {}
        tenant_editable = bool(info.get("tenant_editable", True))
        compliance_locked = bool(info.get("compliance_locked", False))
        approval_needed = bool(info.get("requires_approval", False))

        if (compliance_locked or not tenant_editable) and not (
            actor_is_superadmin and force_override
        ):
            reason = "compliance_locked" if compliance_locked else "tenant_not_editable"
            blocked[key] = reason
            if approval_needed:
                requires_approval[key] = reason
            continue
        applied[key] = value

    saved = False
    if persist and applied:
        settings = dict(getattr(school, "settings", None) or {})
        settings.update(applied)
        school.settings = settings
        school.save(update_fields=["settings", "updated_at"])
        try:
            from apps.policies.policy_registry import invalidate_policy_cache

            invalidate_policy_cache(school)
        except SOFT_TENANT_CONFIG_ERRORS:
            pass
        saved = True

    return {
        "applied": applied,
        "blocked": blocked,
        "requires_approval": requires_approval,
        "saved": saved,
        "metadata": {k: metadata.get(k, {}) for k in payload.keys()},
    }
