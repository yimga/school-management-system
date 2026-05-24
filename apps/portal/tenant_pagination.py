"""Numbered pagination for tenant portal list views (any school tenant)."""

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


def pagination_extra_query(request: HttpRequest, *, omit: tuple[str, ...] = ("page",)) -> str:
    """Rebuild filter query string for pagination links (preserves status/order/etc.)."""
    params = request.GET.copy()
    for key in omit:
        params.pop(key, None)
    return params.urlencode()
