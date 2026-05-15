"""Shared helpers for tenant-side landers.

Three pieces of shared plumbing every per-domain lander uses:

1. ``student_lookup_field(available)`` — pick the canonical external-id
   field name available on the tenant ``StudentProfile`` (different
   deployments use ``external_id``, ``sis_external_id``, ``source_id``,
   or ``admission_number``).

2. ``filter_to_model_fields(defaults, model)`` — drop keys the tenant
   model doesn't declare. Lets landers send the full canonical row
   without worrying about schema drift across tenants.

3. ``coerce_date`` / ``coerce_int`` / ``coerce_decimal`` / ``truthy`` —
   defensive coercions so a stray empty string or "yes" doesn't crash
   the lander; the row gets quarantined instead.
"""

from __future__ import annotations

import datetime as _dt
from decimal import Decimal, InvalidOperation
from typing import Any


_EXTERNAL_ID_CANDIDATES = ("external_id", "sis_external_id", "source_id", "admission_number")


def student_lookup_field(available: set[str]) -> str:
    for c in _EXTERNAL_ID_CANDIDATES:
        if c in available:
            return c
    return "admission_number"


def staff_lookup_field(available: set[str]) -> str:
    for c in ("external_id", "sis_external_id", "employee_id", "staff_number"):
        if c in available:
            return c
    return "external_id"


def model_field_names(model) -> set[str]:
    return {f.name for f in model._meta.get_fields()}


def filter_to_model_fields(defaults: dict[str, Any], model) -> dict[str, Any]:
    available = model_field_names(model)
    return {k: v for k, v in defaults.items() if k in available and v not in (None, "")}


def truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "t", "present", "primary")


def coerce_date(v: Any) -> _dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v).strip()[:10])
    except (TypeError, ValueError):
        return None


def coerce_int(v: Any) -> int | None:
    if v in (None, ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        try:
            return int(float(str(v).strip()))
        except (TypeError, ValueError):
            return None


def coerce_decimal(v: Any) -> Decimal | None:
    if v in (None, ""):
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    try:
        return Decimal(s)
    except (TypeError, InvalidOperation):
        return None
