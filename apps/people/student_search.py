"""Ranked / bounded student profile search (Postgres FTS + portable fallback)."""

from __future__ import annotations

from django.db import connection
from django.db.models import QuerySet

from apps.siteconfig.list_search import (
    MIN_LIST_SEARCH_LEN,
    apply_bounded_icontains,
    normalize_list_search_query,
)


def _is_postgres() -> bool:
    return "postgresql" in connection.vendor.lower()


def filter_students_by_search(queryset: QuerySet, query: str | None) -> QuerySet:
    """
    Filter ``StudentProfile`` queryset by user query.

    Postgres: ``SearchRank`` on ``search_index`` (requires populated column).
    Other backends: bounded ``icontains`` across index + name fields.
    """
    term = normalize_list_search_query(query)
    if len(term) < MIN_LIST_SEARCH_LEN:
        return queryset

    if _is_postgres():
        try:
            from django.contrib.postgres.search import (
                SearchQuery,
                SearchRank,
                SearchVector,
            )

            vector = SearchVector("search_index", weight="A", config="simple")
            sq = SearchQuery(term, config="simple")
            return (
                queryset.annotate(search_rank=SearchRank(vector, sq))
                .filter(search_rank__gt=0)
                .order_by("-search_rank", "last_name", "first_name")
            )
        except Exception:
            pass

    return apply_bounded_icontains(
        queryset,
        term,
        "search_index",
        "first_name",
        "last_name",
        "admission_number",
        "student_code",
    )


__all__ = ["filter_students_by_search"]
