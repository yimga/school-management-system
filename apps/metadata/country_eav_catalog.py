"""Country-specific EAV field catalog — runtime injection without migrations."""

from __future__ import annotations

from typing import Any

# Platform-wide definitions (school=None). Tenants inherit + may override per school.
COUNTRY_EAV_CATALOG: tuple[dict[str, Any], ...] = (
    {
        "country_codes": ("IN",),
        "entity_type": "people.studentprofile",
        "field_key": "aadhaar_reference",
        "label": "Aadhaar reference (masked)",
        "data_type": "string",
        "required": False,
        "validation": {"pattern": r"^\d{4}-\d{4}-\d{4}$", "store_masked": True},
    },
    {
        "country_codes": ("IN",),
        "entity_type": "people.studentprofile",
        "field_key": "udise_code",
        "label": "UDISE+ school code",
        "data_type": "string",
        "required": False,
    },
    {
        "country_codes": ("AE", "SA", "QA", "BH", "KW", "OM"),
        "entity_type": "people.studentprofile",
        "field_key": "civil_registry_id",
        "label": "Civil registry / national ID",
        "data_type": "string",
        "required": False,
    },
    {
        "country_codes": ("AE", "SA", "QA", "BH", "KW", "OM"),
        "entity_type": "people.teacherprofile",
        "field_key": "iqama_or_residency",
        "label": "Residency permit reference",
        "data_type": "string",
        "required": False,
    },
    {
        "country_codes": ("NG", "GH", "CM", "CI", "SN"),
        "entity_type": "people.studentprofile",
        "field_key": "waec_candidate_number",
        "label": "WAEC candidate number",
        "data_type": "string",
        "required": False,
    },
    {
        "country_codes": ("GB", "IE"),
        "entity_type": "people.studentprofile",
        "field_key": "upn",
        "label": "Unique Pupil Number (UPN)",
        "data_type": "string",
        "required": False,
    },
    {
        "country_codes": ("US", "CA"),
        "entity_type": "people.studentprofile",
        "field_key": "state_student_id",
        "label": "State / provincial student ID",
        "data_type": "string",
        "required": False,
    },
    {
        "country_codes": ("FR", "BE", "CH"),
        "entity_type": "people.studentprofile",
        "field_key": "inep_or_national_id",
        "label": "National student identifier",
        "data_type": "string",
        "required": False,
    },
)


def catalog_entries_for_country(country_code: str | None) -> list[dict[str, Any]]:
    cc = (country_code or "").strip().upper()
    if not cc:
        return []
    return [row for row in COUNTRY_EAV_CATALOG if cc in row.get("country_codes", ())]


def seed_country_eav_definitions(
    *,
    school: Any,
    country_code: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Upsert ``DynamicFieldDefinition`` rows for a tenant's country.

    Returns an honesty payload: ``ok`` is False only when the country has catalog
    entries but none were created/updated (unexpected empty seed). Blank country
    or countries outside the catalog are ``ok=True`` with an explicit ``reason``.
    """
    from apps.metadata.models import DynamicFieldDefinition

    cc = (country_code or getattr(school, "country_code", None) or "").strip().upper()
    entries = catalog_entries_for_country(cc)
    created = updated = skipped = 0
    for row in entries:
        defaults = {
            "label": row["label"],
            "data_type": row.get("data_type", "string"),
            "required": bool(row.get("required")),
            # Carry the catalog's validation/masking contract so pattern +
            # store_masked actually reach the form (regex) + save (masking) path.
            "validation_json": dict(row.get("validation") or {}),
            "is_active": True,
        }
        if dry_run:
            skipped += 1
            continue
        _obj, was_created = DynamicFieldDefinition.objects.update_or_create(
            entity_type=row["entity_type"],
            field_key=row["field_key"],
            school=school,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    result: dict[str, Any] = {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "country": cc,
        "expected": len(entries),
    }
    if not cc:
        result["ok"] = True
        result["reason"] = "no_country_code"
    elif not entries:
        result["ok"] = True
        result["reason"] = "no_catalog_entries"
    else:
        result["ok"] = (created + updated + skipped) > 0
        if not result["ok"]:
            result["reason"] = "catalog_entries_not_persisted"
    return result


def seed_platform_eav_baseline(*, dry_run: bool = False) -> dict[str, int]:
    """Seed platform-wide (school=null) definitions shared by all tenants."""
    from apps.metadata.models import DynamicFieldDefinition

    created = updated = 0
    baseline = (
        {
            "entity_type": "people.studentprofile",
            "field_key": "preferred_pronouns",
            "label": "Preferred pronouns",
            "data_type": "string",
        },
        {
            "entity_type": "people.studentprofile",
            "field_key": "emergency_contact_v2",
            "label": "Emergency contact (structured)",
            "data_type": "json",
        },
    )
    for row in baseline:
        if dry_run:
            continue
        _obj, was_created = DynamicFieldDefinition.objects.update_or_create(
            entity_type=row["entity_type"],
            field_key=row["field_key"],
            school=None,
            defaults={
                "label": row["label"],
                "data_type": row["data_type"],
                "is_active": True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated}
