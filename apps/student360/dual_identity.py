"""Student identity matrix across school and program contexts."""

from __future__ import annotations

from typing import Any, Iterable


def build_identity_matrix(
    student: Any,
    *,
    degree_enrollments: Iterable[Any] | None = None,
) -> list[dict[str, Any]]:
    """Project one student identity into its active learning contexts."""
    matrix: list[dict[str, Any]] = []
    classroom = getattr(student, "classroom", None)
    academic_year = getattr(student, "academic_year", None)
    specialty = getattr(student, "specialty", None)
    if classroom is not None or academic_year is not None:
        matrix.append(
            {
                "identity_type": "school",
                "label": getattr(classroom, "name", "") or "Primary school context",
                "schedule_mode": "day_school",
                "academic_year": getattr(academic_year, "name", "") or "",
                "specialty": getattr(specialty, "name", "") or "",
                "program_id": None,
            }
        )

    if degree_enrollments is None:
        manager = getattr(student, "degree_enrollments", None)
        degree_enrollments = (
            manager.filter(is_active=True).select_related("program")
            if manager is not None
            else ()
        )

    for enrollment in degree_enrollments:
        if not getattr(enrollment, "is_active", True):
            continue
        program = getattr(enrollment, "program", None)
        if program is None:
            continue
        requirements = getattr(program, "requirements_json", None) or {}
        matrix.append(
            {
                "identity_type": "program",
                "label": getattr(program, "name", "") or "Program",
                "schedule_mode": str(
                    requirements.get("schedule_mode") or "program"
                ),
                "academic_year": "",
                "specialty": "",
                "program_id": getattr(program, "pk", None),
                "meeting_windows": list(requirements.get("meeting_windows") or []),
                "transcript_track": getattr(program, "transcript_track", ""),
                "start_date": getattr(enrollment, "start_date", None),
            }
        )
    return matrix


__all__ = ["build_identity_matrix"]
