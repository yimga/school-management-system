"""Shared numbered pagination for control-plane operator list views."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.http import HttpRequest


def paginate_for_request(
    request: HttpRequest,
    queryset_or_sequence,
    *,
    per_page: int = 25,
):
    """Return a ``Page`` for ``?page=`` (defaults to page 1)."""
    return Paginator(queryset_or_sequence, per_page).get_page(
        request.GET.get("page") or 1
    )
