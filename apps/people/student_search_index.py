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
    parts = [
        getattr(student, "first_name", ""),
        getattr(student, "last_name", ""),
        getattr(student, "student_code", ""),
        getattr(student, "admission_number", ""),
        email,
    ]
    if getattr(student, "pk", None) is not None:
        try:
            from apps.metadata.services import get_dynamic_field_map

            for _key, val in get_dynamic_field_map(student).items():
                if val is not None and str(val).strip():
                    parts.append(str(val))
        except Exception:
            pass
    return build_search_index_row(*parts)


__all__ = ["build_student_search_index"]
