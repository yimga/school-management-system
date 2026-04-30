"""
Stable JSON envelope for integrator-facing APIs (developer platform contract).

Use for new `/api/v2/` routes and OAuth responses; migrate `/api/v1/` incrementally.
"""

from __future__ import annotations

from typing import Any

from django.core.paginator import Paginator
from django.http import HttpRequest, JsonResponse


CONTRACT_VERSION = "2026.04"


def api_success(
    data: dict[str, Any] | list[Any],
    *,
    status: int = 200,
    meta: dict[str, Any] | None = None,
) -> JsonResponse:
    body: dict[str, Any] = {
        "ok": True,
        "contract_version": CONTRACT_VERSION,
        "data": data,
    }
    if meta:
        body["meta"] = meta
    return JsonResponse(body, status=status)


def api_error(
    code: str,
    message: str,
    *,
    status: int,
    detail: str | None = None,
    field_errors: dict[str, list[str]] | None = None,
) -> JsonResponse:
    err: dict[str, Any] = {"code": code, "message": message}
    if detail:
        err["detail"] = detail
    body: dict[str, Any] = {
        "ok": False,
        "contract_version": CONTRACT_VERSION,
        "errors": [err],
    }
    if field_errors:
        body["field_errors"] = field_errors
    return JsonResponse(body, status=status)


def parse_pagination(
    request: HttpRequest,
    *,
    default_page_size: int = 25,
    max_page_size: int = 100,
) -> tuple[int, int]:
    """Return (page number 1-based, page_size)."""
    try:
        page = max(1, int(request.GET.get("page", "1")))
    except (TypeError, ValueError):
        page = 1
    try:
        raw = int(request.GET.get("page_size", str(default_page_size)))
    except (TypeError, ValueError):
        raw = default_page_size
    page_size = min(max(1, raw), max_page_size)
    return page, page_size


def paginate_queryset(request: HttpRequest, qs, *, default_page_size: int = 25):
    """Return (page_obj, meta dict) using Django Paginator."""
    page_num, page_size = parse_pagination(
        request, default_page_size=default_page_size
    )
    paginator = Paginator(qs, page_size)
    page_obj = paginator.get_page(page_num)
    meta = {
        "page": page_obj.number,
        "page_size": page_size,
        "total_pages": paginator.num_pages,
        "total_count": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
    }
    return page_obj, meta
