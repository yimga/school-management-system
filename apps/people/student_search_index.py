"""Precomputed student list search index (Google pillar)."""

from __future__ import annotations

from typing import Any

from apps.siteconfig.list_search import build_search_index_row


def build_student_search_index(student: Any) -> str:
    """Build lowercase search_index row for FTS / icontains fallback.

    Metric #5: when a FieldCatalogEntry exists for a dynamic field_key, honor
    ``is_indexed`` (skip non-indexed catalog fields). Keys with no catalog row
    remain searchable for legacy custom_attributes back-compat.
    """
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
            from apps.metadata.models import FieldCatalogEntry
            from apps.metadata.services import get_dynamic_field_map

            field_map = get_dynamic_field_map(student)
            keys = [k for k, v in field_map.items() if v is not None and str(v).strip()]
            indexed_by_name: dict[str, bool] = {}
            if keys:
                for row in FieldCatalogEntry.objects.filter(field_name__in=keys).only(
                    "field_name", "is_indexed"
                ):
                    # Any True wins if duplicates exist across entities.
                    indexed_by_name[row.field_name] = indexed_by_name.get(
                        row.field_name, False
                    ) or bool(row.is_indexed)
            for key in keys:
                if key in indexed_by_name and not indexed_by_name[key]:
                    continue
                parts.append(str(field_map[key]))
        except Exception:
            pass
    return build_search_index_row(*parts)


__all__ = ["build_student_search_index"]
