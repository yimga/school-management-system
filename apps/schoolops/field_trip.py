"""Field-trip compliance: consent + offline medical checklist (Wave D — logistics).

Two pieces:
  * ``create_field_trip_consent`` reuses the existing e-sign pipeline
    (``compliance.ConsentRequest`` — parents sign ``ConsentRecord`` rows).
  * ``build_medical_checklist`` compiles each traveller's allergy / medication /
    medical notes + emergency contact into a plain structure a supervising
    teacher can carry **offline** on the trip.

The checklist is a CONFIDENTIAL OPERATIONAL document for the supervising adult —
unlike the auditor view, it is *not* PII-masked, because the teacher needs the
child's real name + allergens + emergency contact to keep them safe.

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave D) and register row ``field-trip-compliance``.
"""

from __future__ import annotations

from typing import Any, Iterable

FIELD_TRIP_CATEGORY = "field_trip"


def create_field_trip_consent(
    *, school_id, title: str, description: str = "", due_date=None
):
    """Get-or-create a field-trip consent request (parents sign ConsentRecords against it).

    Idempotent on (school, category, title): re-running the field-trip wizard
    authorization step — e.g. editing it after completion — returns the existing
    request for the same trip instead of spawning a duplicate. A different trip
    title yields a distinct request, as intended.
    """
    from apps.compliance.models import ConsentRequest

    safe_title = (title or "Field trip").strip()[:255]
    req, _created = ConsentRequest.objects.get_or_create(
        school_id=school_id,
        category=FIELD_TRIP_CATEGORY,
        title=safe_title,
        defaults={
            "description": description or "",
            "due_date": due_date,
            "is_active": True,
        },
    )
    return req


def _classify_health(student_id, school_id) -> dict[str, list[str]]:
    from apps.schoolops.models import HealthRecord

    out: dict[str, list[str]] = {"allergies": [], "medications": [], "other_medical": []}
    rows = HealthRecord.objects.filter(school_id=school_id, student_id=student_id)
    for row in rows:
        rtype = (row.record_type or "").lower()
        note = (row.notes or "").strip()
        if not note:
            continue
        if "allerg" in rtype:
            out["allergies"].append(note)
        elif "medic" in rtype or "drug" in rtype or "prescription" in rtype:
            out["medications"].append(note)
        else:
            out["other_medical"].append(note)
    return out


def build_medical_checklist(school_id, student_ids: Iterable) -> list[dict[str, Any]]:
    """Confidential, offline-carryable medical checklist for the trip's travellers."""
    from apps.people.models import StudentProfile

    ids = [s for s in (student_ids or []) if s]
    students = StudentProfile.objects.filter(school_id=school_id, pk__in=ids)
    checklist: list[dict[str, Any]] = []
    for student in students:
        health = _classify_health(student.pk, school_id)
        classroom = getattr(student, "classroom", None)
        checklist.append(
            {
                "ref": getattr(student, "student_code", "") or str(student.pk),
                "name": f"{student.first_name} {student.last_name}".strip(),
                "class": getattr(classroom, "name", "") if classroom else "",
                "allergies": health["allergies"],
                "medications": health["medications"],
                "other_medical": health["other_medical"],
                "emergency_contact": (getattr(student, "parent_phone", "") or "").strip(),
                "has_medical_flag": bool(
                    health["allergies"] or health["medications"] or health["other_medical"]
                ),
            }
        )
    return checklist
