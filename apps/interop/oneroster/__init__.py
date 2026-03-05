"""
OneRoster 1.1 adapter: canonical models → OneRoster JSON.
"""

from .adapter import (
    build_manifest_resources,
    classroom_to_oneroster,
    enrollment_to_oneroster,
    student_to_oneroster,
    teacher_to_oneroster,
)

__all__ = [
    "build_manifest_resources",
    "classroom_to_oneroster",
    "enrollment_to_oneroster",
    "student_to_oneroster",
    "teacher_to_oneroster",
]
