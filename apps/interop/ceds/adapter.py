"""
CEDS mapping: RunMyCampus canonical -> CEDS elements (K12 student, enrollment, etc.) for US reporting.
Reference: CEDS element IDs and definitions (K12Student, K12StudentEnrollment, etc.).
"""

from __future__ import annotations

from typing import Any


def student_to_ceds(student: Any, school: Any) -> dict[str, Any]:
    """
    Map StudentProfile to CEDS-aligned K12 student record.
    Uses CEDS-aligned element names where applicable.
    """
    return {
        "K12StudentId": str(student.pk),
        "PersonId": str(getattr(student, "user_id", "") or student.pk),
        "FirstName": getattr(student, "first_name", "") or "",
        "LastName": getattr(student, "last_name", "") or "",
        "BirthDate": str(student.date_of_birth) if getattr(student, "date_of_birth", None) else None,
        "Gender": getattr(student, "gender", "") or "",
        "K12StudentUniqueId": getattr(student, "student_code", None) or getattr(student, "admission_number", None) or str(student.pk),
        "OrganizationId": school.pk,
        "OrganizationName": getattr(school, "name", "") or "",
    }


def enrollment_to_ceds(student: Any, school: Any, classroom: Any = None) -> dict[str, Any]:
    """
    Map StudentProfile (+ optional Classroom) to CEDS K12 enrollment elements.
    """
    entry_date = getattr(student, "joined_date", None) or getattr(school, "created_at", None)
    entry_date_str = str(entry_date)[:10] if entry_date else None
    if entry_date and hasattr(entry_date, "date"):
        entry_date_str = str(entry_date.date())
    return {
        "K12StudentEnrollmentId": f"{student.pk}:{getattr(classroom, 'pk', '') or 'school'}",
        "K12StudentId": str(student.pk),
        "OrganizationId": school.pk,
        "EntryDate": entry_date_str,
        "GradeLevel": getattr(student, "section", "") or "Ungraded",
        "SectionId": str(classroom.pk) if classroom else None,
        "SectionName": getattr(classroom, "name", "") if classroom else None,
    }


def grade_to_ceds(evaluation: Any, school: Any) -> dict[str, Any]:
    """
    Map Evaluation to CEDS-aligned grade/assessment outcome.
    """
    student = getattr(evaluation, "student", None)
    if not student:
        return {}
    numeric = None
    for attr in ("exam_score", "seq2_score", "seq1_score", "test2", "test1"):
        val = getattr(evaluation, attr, None)
        if val is not None:
            numeric = float(val)
            break
    subject_assignment = getattr(evaluation, "subject_assignment", None)
    return {
        "GradeId": str(evaluation.pk),
        "K12StudentId": str(student.pk),
        "SectionId": str(subject_assignment.pk) if subject_assignment else None,
        "NumericGrade": numeric,
        "LetterGrade": _numeric_to_letter(numeric) if numeric is not None else None,
    }


def _numeric_to_letter(numeric: float) -> str:
    if numeric >= 18:
        return "A"
    if numeric >= 16:
        return "B"
    if numeric >= 14:
        return "C"
    if numeric >= 12:
        return "D"
    return "F"
