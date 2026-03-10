"""
F3: One-record story — single student/person view across modules.
"""
from __future__ import annotations

from typing import Any


def get_student_one_record(school_id: Any, student_id: Any) -> dict[str, Any]:
    """Aggregate key records for one student (academics, finance, attendance, communications) for unified view."""
    return {
        "student_id": str(student_id),
        "school_id": str(school_id),
        "sections": ["profile", "academics", "attendance", "finance", "communications"],
        "data": {},
    }
