"""Non-destructive PII masking for read-only external-auditor views (Wave E).

Unlike ``gdpr_services.gdpr_scrub_student`` (which *destructively* anonymises a
record), these helpers return a masked *projection* for display — the stored
data is never altered. An external inspector verifying compliance needs to see
that records exist and are well-formed, not the children's identities.

Masking rules: names → initials, DOB → year only, guardian phone → withheld,
keep operational/non-identifying fields (class, status, gender).
"""

from __future__ import annotations

from typing import Any


def _initial(value: Any) -> str:
    text = str(value or "").strip()
    return f"{text[0].upper()}." if text else ""


def _birth_year(dob: Any):
    """Year only, robust to a date object or an ISO string."""
    if dob is None or dob == "":
        return None
    year = getattr(dob, "year", None)
    if year is not None:
        return year
    text = str(dob)[:4]
    return int(text) if text.isdigit() else None


def mask_student_for_auditor(student) -> dict[str, Any]:
    """Return a PII-masked, read-only projection of a student record."""
    classroom = getattr(student, "classroom", None)
    return {
        "ref": getattr(student, "student_code", "") or str(getattr(student, "id", "")),
        "initials": f"{_initial(getattr(student, 'first_name', ''))}{_initial(getattr(student, 'last_name', ''))}",
        "birth_year": _birth_year(getattr(student, "date_of_birth", None)),
        "gender": getattr(student, "gender", "") or "",
        "status": getattr(student, "status", "") or "",
        "class": getattr(classroom, "name", "") if classroom else "",
        "guardian_contact": "withheld",
    }


def mask_roster_for_auditor(students) -> list[dict[str, Any]]:
    return [mask_student_for_auditor(s) for s in students]
