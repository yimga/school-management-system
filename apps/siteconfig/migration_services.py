"""
Phase 10: Migration Cloud services.

These helpers power registry-aware validation for control-plane migration
governance and tenant import readiness.
"""
from __future__ import annotations

from typing import Any

from apps.registries.models import (
    EducationLevelRegistry,
    FeeCategoryRegistry,
    GradeScaleRegistry,
)
from apps.siteconfig.global_catalog import GlobalGeoCatalog


def _normalize_token(value: Any) -> str:
    return str(value or "").strip()


def _normalize_country_alpha2(value: Any) -> str:
    token = _normalize_token(value)
    if not token:
        return ""
    alpha2 = GlobalGeoCatalog.alpha2_for_country(token)
    if alpha2:
        return alpha2.upper()
    normalized = GlobalGeoCatalog.normalize_country_code(token)
    alpha2 = GlobalGeoCatalog.alpha2_for_country(normalized)
    return (alpha2 or token[:2]).upper()


def _school_country(school) -> str:
    if school is None:
        return ""
    return _normalize_country_alpha2(
        getattr(school, "country_code", None)
        or getattr(getattr(school, "default_region", None), "code", None)
        or getattr(school, "default_region_id", None)
    )


def _find_registry_match(model, source_code: str, *, country_code: str = "", name_fields: tuple[str, ...] = ()) -> str | None:
    token = _normalize_token(source_code)
    if not token:
        return None
    normalized_upper = token.upper()
    normalized_lower = token.lower()

    qs = model.objects.filter(is_active=True)
    if country_code and hasattr(model, "country_code"):
        scoped = qs.filter(country_code__in=[country_code, ""])
        exact = scoped.filter(code__iexact=normalized_upper).order_by("-country_code").first()
        if exact:
            return str(exact.code)
    exact = qs.filter(code__iexact=normalized_upper).first()
    if exact:
        return str(exact.code)

    for field in name_fields:
        filters = {f"{field}__iexact": token}
        match = qs.filter(**filters).first()
        if match:
            return str(match.code)

    for row in qs:
        metadata = getattr(row, "metadata", {}) or {}
        aliases = metadata.get("aliases") or metadata.get("legacy_codes") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        if any(_normalize_token(alias).lower() == normalized_lower for alias in aliases):
            return str(row.code)
        if hasattr(row, "country_labels"):
            labels = getattr(row, "country_labels", {}) or {}
            if any(_normalize_token(label).lower() == normalized_lower for label in labels.values()):
                return str(row.code)
    return None


def map_education_level(source_code: str, target_country: str, runtime: Any = None) -> str | None:
    del runtime
    country_code = _normalize_country_alpha2(target_country)
    return _find_registry_match(
        EducationLevelRegistry,
        source_code,
        country_code=country_code,
        name_fields=("global_name",),
    )


def map_grade_scale(source_scale: str, target_country: str, runtime: Any = None) -> str | None:
    del runtime
    country_code = _normalize_country_alpha2(target_country)
    return _find_registry_match(
        GradeScaleRegistry,
        source_scale,
        country_code=country_code,
        name_fields=("name", "family"),
    )


def map_fee_category(source_code: str, target_country: str, runtime: Any = None) -> str | None:
    del runtime
    country_code = _normalize_country_alpha2(target_country)
    return _find_registry_match(
        FeeCategoryRegistry,
        source_code,
        country_code=country_code,
        name_fields=("name", "category"),
    )


def validate_migration_mapping(mapping: dict[str, Any], school: Any = None) -> list[str]:
    """
    Validate migration metadata against registries.

    Accepted keys:
    - education_level / education_levels
    - grade_scale / grade_scales
    - fee_category / fee_categories
    - required / target_fields
    """
    if not isinstance(mapping, dict):
        return ["Migration mapping must be a dictionary."]

    warnings: list[str] = []
    country_code = _school_country(school) or _normalize_country_alpha2(mapping.get("country_code"))

    target_fields = mapping.get("target_fields") or []
    required_fields = mapping.get("required") or []
    if required_fields and not target_fields:
        warnings.append("Migration profile declares required fields without target_fields.")
    if target_fields and required_fields:
        target_set = {str(field).strip() for field in target_fields if str(field).strip()}
        missing_required = [str(field).strip() for field in required_fields if str(field).strip() and str(field).strip() not in target_set]
        if missing_required:
            warnings.append(f"Required fields missing from target_fields: {', '.join(sorted(missing_required))}.")

    def _validate_many(key_single: str, key_plural: str, resolver, label: str):
        raw_values = mapping.get(key_plural)
        if raw_values is None:
            raw_single = mapping.get(key_single)
            raw_values = [] if raw_single in (None, "") else [raw_single]
        if isinstance(raw_values, str):
            raw_values = [part.strip() for part in raw_values.split(",") if part.strip()]
        if not isinstance(raw_values, (list, tuple)):
            raw_values = [raw_values]
        for raw in raw_values:
            token = _normalize_token(raw)
            if token and resolver(token, country_code, runtime=None) is None:
                scope = f" for {country_code}" if country_code else ""
                warnings.append(f"Unknown {label} '{token}'{scope}.")

    _validate_many("education_level", "education_levels", map_education_level, "education level")
    _validate_many("grade_scale", "grade_scales", map_grade_scale, "grade scale")
    _validate_many("fee_category", "fee_categories", map_fee_category, "fee category")

    return warnings


def dry_run_import(source_profile: str, payload: dict[str, Any], school: Any = None) -> dict[str, Any]:
    """
    Registry-aware dry run for Migration Cloud governance.

    This is intentionally non-destructive and lightweight: it validates profile
    shape, required fields, and registry-bound values without writing.
    """
    from apps.automation.models import MigrationProfile

    profile = None
    if isinstance(source_profile, MigrationProfile):
        profile = source_profile
    else:
        profile = MigrationProfile.objects.filter(slug=str(source_profile or "").strip()).first()

    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        rows = []
    mapping = payload.get("mapping") if isinstance(payload, dict) else {}
    if not isinstance(mapping, dict):
        mapping = {}

    warnings: list[str] = []
    errors: list[str] = []
    matched_rows = 0
    required_fields: list[str] = []
    target_fields: list[str] = []

    if profile is None:
        errors.append(f"Unknown migration profile: {source_profile}.")
    else:
        config = profile.config or {}
        target_fields = [str(field).strip() for field in config.get("target_fields", []) if str(field).strip()]
        required_fields = [str(field).strip() for field in config.get("required", []) if str(field).strip()]
        warnings.extend(validate_migration_mapping(config, school=school))

    target_field_set = set(target_fields)
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"Row {idx}: expected an object/dictionary.")
            continue
        missing = [field for field in required_fields if not _normalize_token(row.get(field))]
        if missing:
            errors.append(f"Row {idx}: missing required fields {', '.join(missing)}.")
            continue
        unknown_fields = [key for key in row.keys() if target_field_set and str(key).strip() not in target_field_set]
        if unknown_fields and profile is not None:
            warnings.append(f"Row {idx}: unmapped fields {', '.join(sorted(str(field) for field in unknown_fields[:10]))}.")
        matched_rows += 1

        row_mapping = {
            "education_level": row.get("education_level"),
            "grade_scale": row.get("grade_scale"),
            "fee_category": row.get("fee_category"),
            "country_code": _school_country(school),
        }
        row_warnings = validate_migration_mapping(row_mapping, school=school)
        for warning in row_warnings:
            warnings.append(f"Row {idx}: {warning}")

    status = "success"
    if errors and matched_rows == 0:
        status = "failed"
    elif errors:
        status = "partial"

    return {
        "ok": status != "failed",
        "status": status,
        "profile": getattr(profile, "slug", str(source_profile or "")),
        "rows_affected": len(rows),
        "matched_rows": matched_rows,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "required_fields": required_fields,
        "target_fields": target_fields,
        "mapping": mapping,
        "warnings": warnings[:50],
        "errors": errors[:50],
    }
