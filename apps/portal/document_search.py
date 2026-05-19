"""Portal document library search (Postgres FTS on search_index + fallback)."""

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


def filter_documents_by_search(queryset: QuerySet, query: str | None) -> QuerySet:
    """Filter portal documents using precomputed ``search_index`` when possible."""
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

            vector = (
                SearchVector("search_index", weight="A", config="simple")
                + SearchVector("title", weight="B", config="simple")
            )
            sq = SearchQuery(term, config="simple")
            return (
                queryset.annotate(doc_search_rank=SearchRank(vector, sq))
                .filter(doc_search_rank__gt=0)
                .order_by("-doc_search_rank", "-created_at")
            )
        except Exception:
            pass

    qs = queryset.filter(search_index__icontains=term.lower())
    return apply_bounded_icontains(qs, term, "title", "description")


__all__ = ["filter_documents_by_search"]
