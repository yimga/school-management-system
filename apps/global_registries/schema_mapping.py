"""
Universal field schema mapping registry.

Maps tenant-custom field names onto canonical global field types (identity,
demographic, contact, enrollment, guardian, academic, attendance,
finance_summary, medical, compliance, consent, curriculum, dual_profile).
Used by interop transfer envelopes to fail loudly when a transferable record
would lose information at a boundary.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable


logger = logging.getLogger(__name__)


CANONICAL_FIELD_TYPES = frozenset(
    {
        "identity",
        "demographic",
        "contact",
        "enrollment",
        "guardian",
        "academic",
        "attendance",
        "finance_summary",
        "medical",
        "compliance",
        "consent",
        "curriculum",
        "dual_profile",
    }
)


class SchemaMappingError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalField:
    key: str
    canonical_type: str
    label: str
    transferable: bool = True
    pii: bool = False


# Minimal canonical registry — extended via register_field at app start.
_CORE_FIELDS: tuple[CanonicalField, ...] = (
    CanonicalField("identity.given_name", "identity", "Given name", True, True),
    CanonicalField("identity.family_name", "identity", "Family name", True, True),
    CanonicalField("identity.date_of_birth", "demographic", "Date of birth", True, True),
    CanonicalField("contact.primary_email", "contact", "Primary email", True, True),
    CanonicalField("contact.primary_phone", "contact", "Primary phone", True, True),
    CanonicalField("enrollment.grade", "enrollment", "Grade / form level", True, False),
    CanonicalField("enrollment.section", "enrollment", "Class section", True, False),
    CanonicalField("enrollment.start_date", "enrollment", "Enrollment start date", True, False),
    CanonicalField("guardian.relationship", "guardian", "Guardian relationship", True, False),
    CanonicalField("guardian.primary_contact", "guardian", "Guardian primary contact", True, True),
    CanonicalField("academic.transcript_year", "academic", "Transcript year", True, False),
    CanonicalField("academic.average", "academic", "Period average", True, False),
    CanonicalField("attendance.percent_term", "attendance", "Term attendance percent", True, False),
    CanonicalField("finance_summary.balance", "finance_summary", "Outstanding balance (summary only)", True, False),
    CanonicalField("medical.allergies", "medical", "Known allergies summary", False, True),
    CanonicalField("medical.iep_flag", "medical", "IEP indicator", True, False),
    CanonicalField("compliance.consent_records", "consent", "Consent records summary", True, False),
    CanonicalField("curriculum.framework_code", "curriculum", "Curriculum framework code", True, False),
    CanonicalField("dual_profile.formal_id", "dual_profile", "Formal-system identifier", True, True),
    CanonicalField("dual_profile.academy_id", "dual_profile", "Private-academy identifier", True, True),
)


_REGISTRY: dict[str, CanonicalField] = {f.key: f for f in _CORE_FIELDS}


def canonical_fields() -> tuple[CanonicalField, ...]:
    return tuple(_REGISTRY.values())


def register_field(field: CanonicalField) -> None:
    if field.canonical_type not in CANONICAL_FIELD_TYPES:
        raise SchemaMappingError(
            f"unknown canonical_type {field.canonical_type!r}"
        )
    _REGISTRY[field.key] = field


def lookup(key: str) -> CanonicalField | None:
    return _REGISTRY.get(key)


_SNAKE_RE = re.compile(r"[^a-z0-9]+")


def _normalize(name: str) -> str:
    n = (name or "").strip().lower()
    return _SNAKE_RE.sub("_", n).strip("_")


_HEURISTIC_HINTS: dict[str, str] = {
    "first_name": "identity.given_name",
    "given_name": "identity.given_name",
    "last_name": "identity.family_name",
    "family_name": "identity.family_name",
    "surname": "identity.family_name",
    "dob": "identity.date_of_birth",
    "birthdate": "identity.date_of_birth",
    "date_of_birth": "identity.date_of_birth",
    "email": "contact.primary_email",
    "primary_email": "contact.primary_email",
    "phone": "contact.primary_phone",
    "mobile": "contact.primary_phone",
    "phone_number": "contact.primary_phone",
    "grade": "enrollment.grade",
    "class_level": "enrollment.grade",
    "section": "enrollment.section",
    "form": "enrollment.section",
    "enrollment_start": "enrollment.start_date",
    "guardian_name": "guardian.primary_contact",
    "guardian_phone": "guardian.primary_contact",
    "parent_name": "guardian.primary_contact",
    "transcript_year": "academic.transcript_year",
    "term_average": "academic.average",
    "average": "academic.average",
    "attendance_pct": "attendance.percent_term",
    "outstanding_balance": "finance_summary.balance",
    "allergies": "medical.allergies",
    "iep": "medical.iep_flag",
    "consent": "compliance.consent_records",
    "curriculum": "curriculum.framework_code",
    "formal_id": "dual_profile.formal_id",
    "academy_id": "dual_profile.academy_id",
}


def map_custom_field(name: str) -> CanonicalField | None:
    normalized = _normalize(name)
    if not normalized:
        return None
    hint = _HEURISTIC_HINTS.get(normalized)
    if hint:
        return _REGISTRY.get(hint)
    return None


@dataclass
class MappingValidation:
    ok: bool
    unmapped_keys: list[str]
    mapped: dict[str, str]


def validate_custom_mapping(
    *,
    custom_field_keys: Iterable[str],
    transferable_only: bool = True,
) -> MappingValidation:
    mapped: dict[str, str] = {}
    unmapped: list[str] = []
    for raw in custom_field_keys:
        cf = map_custom_field(raw)
        if cf is None or (transferable_only and not cf.transferable):
            unmapped.append(raw)
        else:
            mapped[raw] = cf.key
    ok = not unmapped
    logger.info(
        "schema_mapping.validate ok=%s mapped=%d unmapped=%d",
        ok,
        len(mapped),
        len(unmapped),
        extra={"scope": "schema_mapping.validate"},
    )
    return MappingValidation(ok=ok, unmapped_keys=unmapped, mapped=mapped)


__all__ = [
    "CANONICAL_FIELD_TYPES",
    "CanonicalField",
    "MappingValidation",
    "SchemaMappingError",
    "canonical_fields",
    "lookup",
    "map_custom_field",
    "register_field",
    "validate_custom_mapping",
]
