"""v4.00.92 Wave 25 M1 — Shared OneRoster v1.2 query helpers.

Centralizes the ``?sort=`` + ``?orderBy=`` + ``?fields=`` helpers that were
previously private to ``oneroster_demographics``. The Wave 25 sweep wires
these helpers into the 6 main GET collection endpoints (orgs, schools,
users, classes, courses, enrollments) so the entire Roster Service surface
honors the v1.2 § 4.13 query contract identically.

Public helpers
--------------
``apply_sort(items, sort_field, order_by) -> list[dict]``
    Sort items per OneRoster v1.2 spec § 4.13 (sort + orderBy). Unknown
    fields no-op. Bad orderBy falls back to asc. Empty sort field
    short-circuits to no-op (operator-facing surface).

``parse_fields_mask(raw) -> tuple[str, ...] | None``
    Parse a comma-separated field mask. ``None`` when no mask is active.

``apply_fields_mask(rec, mask) -> dict``
    Filter a record to only the requested fields plus the always-pinned
    ``sourcedId``.

``apply_filter(items, expr) -> list[dict]``
    Wrap ``oneroster_filter.apply_filter`` for symmetry with the other
    helpers (so callers can import a single module).

``apply_pipeline(request, items, *, default_envelope_key) -> tuple``
    Apply the standard Roster Service v1.2 pipeline:
    filter -> sort -> fields-mask -> pagination. Returns
    ``(page, meta_dict)`` matching the existing ``_envelope`` convention
    in ``oneroster.py``.

The historical private aliases in ``oneroster_demographics`` (``_apply_sort``,
``_parse_fields_mask``, ``_apply_fields_mask``) re-export the public
helpers for back-compat — older code that imports them keeps working.
"""
from __future__ import annotations

from typing import Any

from django.http import HttpRequest


_SORT_ALLOW_DESC = frozenset(("desc", "DESC"))
_FIELDS_MASK_PIN: tuple[str, ...] = ("sourcedId",)


def apply_sort(items: list[dict[str, Any]], sort_field: str, order_by: str) -> list[dict[str, Any]]:
    """Sort items per OneRoster v1.2 spec § 4.13 (sort + orderBy).

    Unknown fields no-op (no order change). Bad orderBy values fall back to
    'asc'. Empty string short-circuits to no-op (operator-facing surface —
    don't 400).
    """
    field = (sort_field or "").strip()
    if not field:
        return items
    direction = (order_by or "").strip()
    reverse = direction in _SORT_ALLOW_DESC
    # Guard against TypeError when the field is missing/None on some rows —
    # coerce to empty string so sort is total. Do NOT 400 on unknown field
    # per the operator-facing-surface contract.
    return sorted(items, key=lambda r: (r.get(field) or ""), reverse=reverse)


def parse_fields_mask(raw: str) -> tuple[str, ...] | None:
    """Return parsed mask tuple or ``None`` when no mask is active."""
    raw = (raw or "").strip()
    if not raw:
        return None
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def apply_fields_mask(rec: dict[str, Any], mask: tuple[str, ...] | None) -> dict[str, Any]:
    """Return a record with only the requested fields (plus sourcedId)."""
    if mask is None:
        return rec
    keep = set(mask) | set(_FIELDS_MASK_PIN)
    return {k: v for k, v in rec.items() if k in keep}


def apply_filter(items: list[dict[str, Any]], expr: str) -> list[dict[str, Any]]:
    """Apply a OneRoster v1.2 ``?filter=`` expression.

    Returns the original ``items`` unchanged on bad / empty expr (the
    parser is fail-safe per its own contract — see ``oneroster_filter``).
    """
    expr = (expr or "").strip()
    if not expr:
        return items
    # Lazy import to avoid a top-level circular import (oneroster_filter is
    # otherwise pure-stdlib so this is cheap).
    from apps.api.oneroster_filter import apply_filter as _apply_filter
    return _apply_filter(items, expr)


def _paginate_local(request: HttpRequest, items: list[Any]) -> tuple[list[Any], dict[str, int]]:
    """Local copy of the pagination contract used by oneroster.py.

    Duplicated here (rather than imported) to avoid a circular import with
    ``apps.api.oneroster`` — that module imports this one to apply the
    pipeline, and re-importing back would cycle. The contract is verbatim
    identical (default 100 / max 1000 / non-negative offset).
    """
    try:
        limit = int(request.GET.get("limit") or 100)
    except (ValueError, TypeError):
        limit = 100
    try:
        offset = int(request.GET.get("offset") or 0)
    except (ValueError, TypeError):
        offset = 0
    limit = max(1, min(1000, limit))
    offset = max(0, offset)
    return items[offset:offset + limit], {
        "limit": limit,
        "offset": offset,
        "totalCount": len(items),
    }


def apply_pipeline(
    request: HttpRequest,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Apply the OneRoster v1.2 query pipeline: filter -> sort -> fields-mask -> page.

    Returns ``(page_items, meta)`` where ``meta`` has the same shape as
    ``oneroster._paginate`` — ``{limit, offset, totalCount}``. The
    ``totalCount`` reflects the post-filter, pre-pagination row count so
    HEAD verb / X-Total-Count consumers see the filtered total.
    """
    items = apply_filter(items, request.GET.get("filter") or "")
    sort_field = (request.GET.get("sort") or "").strip()
    order_by = (request.GET.get("orderBy") or "").strip()
    if sort_field:
        items = apply_sort(items, sort_field, order_by)
    mask = parse_fields_mask(request.GET.get("fields") or "")
    if mask is not None:
        items = [apply_fields_mask(r, mask) for r in items]
    return _paginate_local(request, items)


def total_count_for(request: HttpRequest, items: list[dict[str, Any]]) -> int:
    """Compute the post-filter total-count for HEAD-verb / X-Total-Count.

    Reuses the same filter pipeline so HEAD reports exactly what GET would
    paginate over.
    """
    items = apply_filter(items, request.GET.get("filter") or "")
    return len(items)
