"""
Bounded list-search helpers (Google pillar).

Centralizes icontains query normalization so portal/people list views share
the same min-length, max-length, and wildcard-stripping rules.
"""

from __future__ import annotations

import re

from django.db.models import Q, QuerySet

MIN_LIST_SEARCH_LEN = 2
MAX_LIST_SEARCH_LEN = 128

_WILDCARD_RE = re.compile(r"[%_\\]")


def normalize_list_search_query(raw: str | None) -> str:
    """Strip, cap length, and remove SQL-wildcard characters from user input."""
    q = (raw or "").strip()
    if len(q) > MAX_LIST_SEARCH_LEN:
        q = q[:MAX_LIST_SEARCH_LEN]
    return _WILDCARD_RE.sub("", q)


def tokenize_list_search(query: str | None) -> list[str]:
    """Split normalized query into AND tokens (each min length enforced)."""
    term = normalize_list_search_query(query)
    if len(term) < MIN_LIST_SEARCH_LEN:
        return []
    tokens: list[str] = []
    for piece in term.split():
        piece = piece.strip()
        if len(piece) >= MIN_LIST_SEARCH_LEN:
            tokens.append(piece)
    return tokens or ([term] if len(term) >= MIN_LIST_SEARCH_LEN else [])


def apply_bounded_icontains(
    queryset: QuerySet,
    query: str | None,
    *field_lookups: str,
) -> QuerySet:
    """
    Apply OR'd ``__icontains`` filters when ``query`` meets min length.

    Multi-word queries use AND semantics: every token must match at least one field.
    ``field_lookups`` are ORM paths without the ``__icontains`` suffix.
    """
    tokens = tokenize_list_search(query)
    if not tokens or not field_lookups:
        return queryset
    for token in tokens:
        q_obj = Q()
        for field in field_lookups:
            lookup = field if field.endswith("__icontains") else f"{field}__icontains"
            q_obj |= Q(**{lookup: token})
        queryset = queryset.filter(q_obj)
    return queryset


def build_search_index_row(*parts: str | None) -> str:
    """Normalize free-text parts into a single lowercase search index row."""
    cleaned: list[str] = []
    for part in parts:
        text = normalize_list_search_query(part)
        if text:
            cleaned.append(text.lower())
    return " ".join(cleaned)


__all__ = [
    "MIN_LIST_SEARCH_LEN",
    "MAX_LIST_SEARCH_LEN",
    "apply_bounded_icontains",
    "build_search_index_row",
    "normalize_list_search_query",
    "tokenize_list_search",
]
