"""
Execute governed queries using Django ORM only (validated against ``catalog.DATASETS``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.apps import apps
from django.db.models import Avg, Count, Max, Min, Sum
from .catalog import AGGREGATIONS, DATASETS, MAX_EXPORT_ROWS


class GovernedQueryError(ValueError):
    """Invalid dataset, field, filter, permission, or tenant scope."""


def _get_model(meta: dict):
    path = meta["model"]
    app_label, model_name = path.split(".", 1)
    return apps.get_model(app_label, model_name)


def _user_can_access(user, meta: dict) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    perms: tuple[str, ...] = meta["permissions"]
    return any(user.has_feature_permission(p) for p in perms)


def _validate_fields(meta: dict, fields: list[str]) -> list[str]:
    allowed = set(meta["fields"])
    out = []
    for f in fields:
        if f not in allowed:
            raise GovernedQueryError(f"field not allowed: {f}")
        out.append(f)
    return out or list(meta["fields"])[:8]


def _apply_filters(qs, meta: dict, filters: dict[str, Any]):
    allowed = meta["filters"]
    for key, val in (filters or {}).items():
        if key not in allowed:
            raise GovernedQueryError(f"filter not allowed: {key}")
        qs = qs.filter(**{key: val})
    return qs


def _agg_expr(fn: str, field: str):
    fn_l = fn.lower()
    if fn_l == "count":
        return Count(field)
    if fn_l == "sum":
        return Sum(field)
    if fn_l == "avg":
        return Avg(field)
    if fn_l == "min":
        return Min(field)
    if fn_l == "max":
        return Max(field)
    raise GovernedQueryError(f"aggregation not allowed: {fn}")


def execute_governed_query(
    *,
    user,
    school_id: str | None,
    dataset_id: str,
    fields: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    group_by: list[str] | None = None,
    aggregate: dict[str, Any] | None = None,
    limit: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Returns (rows, meta) where rows are JSON-serializable dicts.

    *aggregate* shape: ``{"fn": "sum", "field": "balance_amount"}`` (optional).
    When aggregate + group_by: returns aggregated rows (still ORM).
    """
    if dataset_id not in DATASETS:
        raise GovernedQueryError(f"unknown dataset: {dataset_id}")

    meta = DATASETS[dataset_id]
    if not _user_can_access(user, meta):
        raise GovernedQueryError("permission denied for dataset")

    tenant_field = meta.get("tenant_field")
    tenant_lookup = (meta.get("tenant_lookup") or "").strip()
    if tenant_lookup and not school_id:
        raise GovernedQueryError("school_id is required for this dataset")
    if tenant_field and not tenant_lookup and not school_id:
        raise GovernedQueryError("school_id is required for this dataset")

    Model = _get_model(meta)
    qs = Model.objects.all()

    if tenant_lookup:
        qs = qs.filter(**{tenant_lookup: school_id})
    elif tenant_field and school_id is not None:
        qs = qs.filter(**{tenant_field: school_id})

    qs = _apply_filters(qs, meta, filters or {})

    lim = min(limit or MAX_EXPORT_ROWS, MAX_EXPORT_ROWS)

    fields_list = _validate_fields(meta, list(fields or []))

    agg_meta = {
        "dataset_id": dataset_id,
        "row_limit": lim,
        "aggregated": bool(group_by and aggregate),
    }

    if group_by and aggregate:
        gb_fields = [x for x in group_by if x in meta["group_by"]]
        if not gb_fields:
            raise GovernedQueryError("group_by required fields missing or not allowed")
        if len(gb_fields) > 2:
            raise GovernedQueryError("at most 2 group_by fields supported")

        fn = aggregate.get("fn") or "count"
        field = aggregate.get("field") or "id"
        if fn.lower() not in AGGREGATIONS:
            raise GovernedQueryError(f"aggregation fn not allowed: {fn}")
        if fn.lower() != "count" and field not in meta["aggregate_fields"]:
            raise GovernedQueryError(f"aggregate field not allowed: {field}")

        ann = _agg_expr(fn, field)
        alias = f"{fn.lower()}_{field}"
        qs = qs.values(*gb_fields).annotate(**{alias: ann}).order_by(*gb_fields)[:lim]

        rows = []
        for row in qs:
            d = dict(row)
            for k, v in list(d.items()):
                if isinstance(v, Decimal):
                    d[k] = float(v)
            rows.append(d)
        return rows, agg_meta

    qs = qs.order_by("id")[:lim]

    row_dicts = list(qs.values(*fields_list))
    for d in row_dicts:
        for k, v in list(d.items()):
            if hasattr(v, "isoformat"):
                d[k] = v.isoformat()
            elif isinstance(v, Decimal):
                d[k] = float(v)
    return row_dicts, agg_meta


def serialize_catalog_for_ui(user) -> dict[str, Any]:
    """Dataset definitions the current user may use (no internal-only keys)."""
    out: dict[str, Any] = {}
    for ds_id, meta in DATASETS.items():
        if not _user_can_access(user, meta):
            continue
        out[ds_id] = {
            "label": meta["label"],
            "fields": list(meta["fields"]),
            "filters": sorted(meta["filters"]),
            "group_by": sorted(meta["group_by"]),
            "aggregations": list(AGGREGATIONS),
            "aggregate_fields": sorted(meta["aggregate_fields"]),
        }
    return out
