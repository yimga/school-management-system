from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone


FIELD_LABELS = {
    "country": "Country",
    "subdivision": "State / province",
    "timezone": "Time zone",
    "currency": "Currency",
    "locale": "Language and locale",
    "calendar": "Calendar system",
    "institution_type": "Institution type",
    "grading_scale": "Grading scale",
    "education_system": "Education system",
}


def _rows(model, *, filters=None) -> list[dict[str, str]]:
    query = model.objects.filter(is_active=True, **(filters or {})).order_by("name")
    return [
        {"value": str(row.pk), "label": f"{row.name} ({row.code})"}
        for row in query[:500]
    ]


def remedy_choices(school, field_key: str) -> list[dict[str, str]]:
    from apps.registries import models as registry_models

    model_names = {
        "country": "CountryRegistry",
        "subdivision": "SubdivisionRegistry",
        "timezone": "TimeZoneRegistry",
        "currency": "CurrencyRegistry",
        "locale": "LocaleRegistry",
        "calendar": "CalendarSystemRegistry",
        "institution_type": "InstitutionTypeRegistry",
        "grading_scale": "GradeScaleRegistry",
        "education_system": "EducationSystemTypeRegistry",
    }
    model = getattr(registry_models, model_names[field_key])
    filters: dict[str, Any] = {}
    if field_key == "subdivision" and getattr(school, "country_code", ""):
        filters["country_id"] = school.country_code
    return _rows(model, filters=filters)


def current_remedy_value(school, field_key: str) -> str:
    settings = dict(getattr(school, "settings", {}) or {})
    values = {
        "country": getattr(school, "country_code", ""),
        "subdivision": getattr(school, "subdivision_id", ""),
        "timezone": getattr(school, "timezone", ""),
        "currency": getattr(school, "currency", ""),
        "locale": getattr(school, "default_language", ""),
        "calendar": settings.get("calendar_system") or settings.get("calendar_system_code"),
        "institution_type": getattr(school, "school_type", ""),
        "grading_scale": settings.get("grading_scale") or settings.get("grading_scale_code"),
        # "Education system" is the education-system TYPE / sector (PUBLIC / PRIVATE /
        # IB / ... — codes in EducationSystemTypeRegistry), which lives on
        # `primary_sector`. It is NOT the language sub-system (FR / EN / INT on
        # `sub_system`). remedy_choices() validates against EducationSystemTypeRegistry,
        # so read/write must target `primary_sector` for the control to be coherent.
        "education_system": getattr(school, "primary_sector", ""),
    }
    return str(values.get(field_key) or "")


def build_direct_remedy(school, field_key: str) -> dict[str, Any] | None:
    if field_key not in FIELD_LABELS:
        return None
    overrides = dict((getattr(school, "settings", {}) or {}).get("setup_registry_overrides") or {})
    return {
        "key": field_key,
        "label": FIELD_LABELS[field_key],
        "current_value": current_remedy_value(school, field_key),
        "choices": remedy_choices(school, field_key),
        "override": overrides.get(field_key) or None,
    }


@transaction.atomic
def apply_direct_remedy(school, *, field_key: str, value: str, actor) -> None:
    if field_key not in FIELD_LABELS:
        raise ValueError("Unknown repair field.")
    valid_values = {row["value"] for row in remedy_choices(school, field_key)}
    if value not in valid_values:
        raise ValueError("Choose an active registry value.")

    settings = dict(school.settings or {})
    overrides = dict(settings.get("setup_registry_overrides") or {})
    overrides.pop(field_key, None)
    settings["setup_registry_overrides"] = overrides
    update_fields = {"settings", "updated_at"}
    if field_key == "country":
        school.country_code = value.upper()[:2]
        school.subdivision = None
        update_fields.update(("country_code", "subdivision"))
    elif field_key == "subdivision":
        school.subdivision_id = value
        update_fields.add("subdivision")
    elif field_key == "timezone":
        school.timezone = value
        update_fields.add("timezone")
    elif field_key == "currency":
        school.currency = value.upper()[:3]
        update_fields.add("currency")
    elif field_key == "locale":
        school.default_language = value.split("-")[0].lower()
        update_fields.add("default_language")
    elif field_key == "calendar":
        settings["calendar_system"] = value
    elif field_key == "institution_type":
        school.school_type = value
        update_fields.add("school_type")
    elif field_key == "grading_scale":
        settings["grading_scale"] = value
    elif field_key == "education_system":
        # Write the chosen EducationSystemTypeRegistry code to `primary_sector`
        # (the sector field the alignment snapshot reads), NOT `sub_system` — the
        # language sub-system (FR/EN/INT) must never receive a curriculum/sector code.
        school.primary_sector = value
        update_fields.add("primary_sector")
    school.settings = settings
    school.save(update_fields=sorted(update_fields))


@transaction.atomic
def override_direct_remedy(school, *, field_key: str, reason: str, actor) -> None:
    if field_key not in FIELD_LABELS:
        raise ValueError("Unknown repair field.")
    reason = str(reason or "").strip()
    if len(reason) < 8:
        raise ValueError("Explain why this finding is a false positive (at least 8 characters).")
    settings = dict(school.settings or {})
    overrides = dict(settings.get("setup_registry_overrides") or {})
    overrides[field_key] = {
        "reason": reason[:500],
        "actor_id": getattr(actor, "pk", None),
        "actor": getattr(actor, "username", "") or "",
        "created_at": timezone.now().isoformat(),
    }
    settings["setup_registry_overrides"] = overrides
    school.settings = settings
    school.save(update_fields=["settings", "updated_at"])
