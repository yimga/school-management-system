"""
Ed-Fi API mapping: RunMyCampus canonical (StudentProfile, Classroom, Evaluation) -> Ed-Fi resource shapes.
Supplies students, studentSchoolAssociations, and student grades for interchange.
"""

from __future__ import annotations

from typing import Any


def student_to_edfi(student: Any, school: Any) -> dict[str, Any]:
    """
    Map StudentProfile to Ed-Fi student resource.
    studentUniqueId is required; we use student_code or admission_number or pk.
    """
    unique_id = (
        getattr(student, "student_code", None)
        or getattr(student, "admission_number", None)
        or str(student.pk)
    )
    return {
        "studentUniqueId": str(unique_id),
        "firstName": getattr(student, "first_name", "") or "",
        "lastSurname": getattr(student, "last_name", "") or "",
        "birthDate": str(student.date_of_birth)
        if getattr(student, "date_of_birth", None)
        else None,
        "genderDescriptor": _gender_to_edfi(getattr(student, "gender", "")),
    }


def student_school_association_to_edfi(student: Any, school: Any) -> dict[str, Any]:
    """
    Map StudentProfile + School to Ed-Fi studentSchoolAssociation.
    schoolReference.schoolId, studentReference.studentUniqueId, entryDate, entryGradeLevelDescriptor required.
    """
    unique_id = (
        getattr(student, "student_code", None)
        or getattr(student, "admission_number", None)
        or str(student.pk)
    )
    entry_date = getattr(student, "joined_date", None) or getattr(
        school, "created_at", None
    )
    entry_date_str = str(entry_date)[:10] if entry_date else None
    if not entry_date_str and hasattr(entry_date, "date"):
        entry_date_str = str(entry_date.date())
    return {
        "schoolReference": {"schoolId": school.pk},
        "studentReference": {"studentUniqueId": str(unique_id)},
        "entryDate": entry_date_str or "2020-09-01",
        "entryGradeLevelDescriptor": _section_to_grade_descriptor(
            getattr(student, "section", "") or "Ungraded"
        ),
        "entryTypeDescriptor": "uri://ed-fi.org/EntryTypeDescriptor#Next year school",
    }


def evaluation_to_edfi_grade(evaluation: Any, school: Any) -> dict[str, Any]:
    """
    Map Evaluation to an Ed-Fi-style grade (simplified).
    Ed-Fi has studentSectionAssociation and grade; we output a minimal grade-like object.
    """
    student = getattr(evaluation, "student", None)
    if not student:
        return {}
    unique_id = (
        getattr(student, "student_code", None)
        or getattr(student, "admission_number", None)
        or str(student.pk)
    )
    subject_assignment = getattr(evaluation, "subject_assignment", None)
    section_id = (
        str(subject_assignment.pk) if subject_assignment else str(evaluation.pk)
    )
    # Numeric grade: prefer exam_score, then seq2, seq1, or test2, test1
    numeric = None
    for attr in ("exam_score", "seq2_score", "seq1_score", "test2", "test1"):
        val = getattr(evaluation, attr, None)
        if val is not None:
            numeric = float(val)
            break
    return {
        "studentReference": {"studentUniqueId": str(unique_id)},
        "sectionReference": {"sectionIdentifier": section_id},
        "letterGradeEarned": _numeric_to_letter(numeric, school=school)
        if numeric is not None
        else None,
        "numericGradeEarned": numeric,
    }


def _gender_to_edfi(gender: str) -> str | None:
    if not gender:
        return None
    g = (gender or "").upper()
    if g in ("MALE", "M"):
        return "uri://ed-fi.org/GenderDescriptor#Male"
    if g in ("FEMALE", "F"):
        return "uri://ed-fi.org/GenderDescriptor#Female"
    return "uri://ed-fi.org/GenderDescriptor#Not Selected"


def _section_to_grade_descriptor(section: str) -> str:
    if not section:
        return "uri://ed-fi.org/GradeLevelDescriptor#Ungraded"
    # Map common section names to Ed-Fi grade descriptor URIs
    s = (section or "").strip().upper()
    for key, uri in [
        ("1", "First grade"),
        ("2", "Second grade"),
        ("3", "Third grade"),
        ("4", "Fourth grade"),
        ("5", "Fifth grade"),
        ("6", "Sixth grade"),
        ("7", "Seventh grade"),
        ("8", "Eighth grade"),
        ("9", "Ninth grade"),
        ("10", "Tenth grade"),
        ("11", "Eleventh grade"),
        ("12", "Twelfth grade"),
    ]:
        if key in s or s == key:
            return f"uri://ed-fi.org/GradeLevelDescriptor#{uri}"
    return "uri://ed-fi.org/GradeLevelDescriptor#Ungraded"


def _numeric_to_letter(numeric: float, school: Any = None) -> str:
    """Convert a numeric grade to a letter, honoring the tenant's grading scale.

    Routes through apps.evals.grading.get_grade_letter so an export from a US K-12 school
    (0-100 scale) does not get F for every score below 18, and a French school (0-20 scale)
    gets A for 18 rather than for 80. Falls back to a 0-20 lookup if the scale can't be
    resolved (preserves pre-existing behavior on legacy callers that don't pass a school).
    """
    try:
        from apps.evals.grading import get_grade_letter, get_scale_for_school

        scale = get_scale_for_school(school) if school is not None else "0-20"
        return get_grade_letter(numeric, scale=scale)
    except (ImportError, AttributeError, KeyError, TypeError, ValueError):
        if numeric >= 18:
            return "A"
        if numeric >= 16:
            return "B"
        if numeric >= 14:
            return "C"
        if numeric >= 12:
            return "D"
        return "F"
