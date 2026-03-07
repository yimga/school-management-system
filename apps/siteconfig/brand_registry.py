from __future__ import annotations

from copy import deepcopy
from typing import Any

from apps.siteconfig.global_catalog import GlobalGeoCatalog


BASELINE_ISCED_LEVELS = {
    "0": "Early childhood education",
    "1": "Primary education",
    "2": "Lower secondary education",
    "3": "Upper secondary education",
    "4": "Post-secondary non-tertiary",
    "5": "Short-cycle tertiary",
    "6": "Bachelor or equivalent",
    "7": "Master or equivalent",
    "8": "Doctoral or equivalent",
}

DEFAULT_LABELS_MAP = {
    "student": "Student",
    "teacher": "Teacher",
    "staff": "Staff",
    "parent": "Parent",
    "principal": "Principal",
}

DEFAULT_COMPLIANCE_CONFIG = {
    "privacy_law": "default",
    "data_residency": "global",
}

DEFAULT_UI_CONFIG = {
    "date_format": "DD/MM/YYYY",
    "number_decimal_separator": ".",
    "number_thousands_separator": ",",
    "is_rtl": False,
}


def _normalize_country_codes(country_code: str | None) -> tuple[str, str]:
    """
    Returns (alpha2, alpha3). Empty strings when unknown.
    """
    raw = (country_code or "").strip()
    alpha3 = GlobalGeoCatalog.normalize_country_code(raw)
    alpha2 = GlobalGeoCatalog.alpha2_for_country(alpha3) if alpha3 else ""
    return alpha2.upper(), alpha3.upper()


def _country_from_school(school) -> tuple[str, str]:
    if school is None:
        return "", ""
    region_code = getattr(school, "default_region_id", "") or ""
    return _normalize_country_codes(region_code)


def _default_marketing_seo(country_name: str, language_code: str) -> dict[str, Any]:
    language = (language_code or "en").split("-", 1)[0].lower()
    if language == "fr":
        return {
            "headline": f"La plateforme scolaire mondiale pour {country_name}",
            "subheadline": "Gestion complete des ecoles, finances et communications.",
            "seo_title": f"RunMyCampus - Logiciel scolaire pour {country_name}",
            "seo_description": "Plateforme multi-tenant pour la gestion scolaire, les notes et la finance.",
        }
    if language == "pt":
        return {
            "headline": f"Plataforma escolar global para {country_name}",
            "subheadline": "Gestao completa para escolas, financas e comunicacao.",
            "seo_title": f"RunMyCampus - Sistema escolar para {country_name}",
            "seo_description": "Plataforma multi-tenant para notas, administracao e financas escolares.",
        }
    return {
        "headline": f"Global School Operations for {country_name}",
        "subheadline": "Secure, multi-tenant school management for academics, finance, and operations.",
        "seo_title": f"RunMyCampus - School Management Platform for {country_name}",
        "seo_description": "Global school management platform with tenant branding, analytics, and compliance controls.",
    }


def _deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _school_label_overrides(school) -> dict[str, Any]:
    from apps.policies.policy_registry import get_effective_policy
    policy = get_effective_policy(school) if school else {}
    labels = policy.get("labels_map")
    if isinstance(labels, dict):
        return labels
    education = policy.get("education_profile") or {}
    if isinstance(education, dict) and isinstance(education.get("labels_map"), dict):
        return education.get("labels_map") or {}
    return {}


def resolve_global_brand_context(
    *,
    school=None,
    country_code: str | None = None,
    language_code: str | None = None,
) -> dict[str, Any]:
    """
    Resolve effective branding/terminology defaults.

    Precedence:
    1. Global defaults (catalog + built-in baseline)
    2. GlobalBrandRegistry row (if available)
    3. Tenant/school label overrides
    """
    alpha2 = ""
    alpha3 = ""
    if school is not None:
        alpha2, alpha3 = _country_from_school(school)
    if not alpha2:
        alpha2, alpha3 = _normalize_country_codes(country_code)

    defaults = GlobalGeoCatalog.country_defaults(alpha3 or alpha2)
    country_name = defaults.get("country_name") or alpha3 or alpha2 or "Global"
    primary_language = (language_code or defaults.get("default_language") or "en").strip() or "en"
    currency_code = (defaults.get("currency") or "USD").strip().upper()

    base_context: dict[str, Any] = {
        "iso_code": alpha2,
        "country_code_alpha3": alpha3,
        "country_name": country_name,
        "primary_language": primary_language,
        "currency_code": currency_code,
        "academic_config": {
            "isced_levels": deepcopy(BASELINE_ISCED_LEVELS),
            "source": "baseline",
        },
        "labels_map": deepcopy(DEFAULT_LABELS_MAP),
        "compliance_config": deepcopy(DEFAULT_COMPLIANCE_CONFIG),
        "seo_config": _default_marketing_seo(country_name, primary_language),
        "ui_config": _deep_merge_dict(
            DEFAULT_UI_CONFIG,
            {
                "date_format": "DD/MM/YYYY",
                "timezone": defaults.get("timezone") or "UTC",
                "locale": primary_language,
            },
        ),
        "source_name": "baseline",
        "source_synced_at": None,
        "is_registry_record": False,
    }

    try:
        from apps.siteconfig.models import GlobalBrandRegistry

        if alpha2:
            row = GlobalBrandRegistry.objects.filter(iso_code=alpha2, is_active=True).first()
        else:
            row = None
    except Exception:
        row = None

    if row is not None:
        base_context["country_name"] = row.country_name or base_context["country_name"]
        base_context["primary_language"] = row.primary_language or base_context["primary_language"]
        base_context["currency_code"] = (row.currency_code or base_context["currency_code"]).upper()
        base_context["academic_config"] = _deep_merge_dict(
            base_context["academic_config"],
            row.academic_config if isinstance(row.academic_config, dict) else {},
        )
        base_context["labels_map"] = _deep_merge_dict(
            base_context["labels_map"],
            row.labels_map if isinstance(row.labels_map, dict) else {},
        )
        base_context["compliance_config"] = _deep_merge_dict(
            base_context["compliance_config"],
            row.compliance_config if isinstance(row.compliance_config, dict) else {},
        )
        base_context["seo_config"] = _deep_merge_dict(
            base_context["seo_config"],
            row.seo_config if isinstance(row.seo_config, dict) else {},
        )
        base_context["ui_config"] = _deep_merge_dict(
            base_context["ui_config"],
            row.ui_config if isinstance(row.ui_config, dict) else {},
        )
        base_context["source_name"] = row.source_name or "global_brand_registry"
        base_context["source_synced_at"] = row.source_synced_at
        base_context["is_registry_record"] = True

    if school is not None:
        base_context["labels_map"] = _deep_merge_dict(base_context["labels_map"], _school_label_overrides(school))

    return base_context
