"""Precomputed student list search index (Google pillar)."""

from __future__ import annotations

from typing import Any

from apps.siteconfig.list_search import build_search_index_row


def build_student_search_index(student: Any) -> str:
    """Build lowercase search_index row for FTS / icontains fallback."""
    email = ""
    user = getattr(student, "user", None)
    if user is not None:
        email = (getattr(user, "email", "") or "").strip()
    return build_search_index_row(
        getattr(student, "first_name", ""),
        getattr(student, "last_name", ""),
        getattr(student, "student_code", ""),
        getattr(student, "admission_number", ""),
        email,
    )


__all__ = ["build_student_search_index"]
