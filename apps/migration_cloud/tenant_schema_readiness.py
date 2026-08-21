"""Migration Cloud tenant schema readiness gate.

Post-apply hooks (gap-fill, guardian directory, staff-role backfill) query tenant
models whose columns must exist in the tenant schema. When migrations never reached
a tenant, apply "succeeds" with hundreds of open issues and repair loops forever.

This module detects column drift inside ``schema_context``, attempts the same
best-effort heals provisioning uses (``run_tenant_column_repairs`` +
``ensure_models_columns``), and returns an operator-facing readiness result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.apps import apps as django_apps


@dataclass(frozen=True)
class TenantSchemaReadiness:
    schema_name: str
    ready: bool
    missing_labels: tuple[str, ...] = ()
    repaired_labels: tuple[str, ...] = ()
    repair_attempted: bool = False


def _models_for_missing(
    missing: list[tuple[str, str, str, str]],
) -> list[type]:
    seen: set[tuple[str, str]] = set()
    models: list[type] = []
    for app_label, model_name, _table, _column in missing:
        key = (app_label, model_name)
        if key in seen:
            continue
        seen.add(key)
        try:
            models.append(django_apps.get_model(app_label, model_name))
        except LookupError:
            continue
    return models


def assess_tenant_schema_readiness(
    schema_name: str,
    *,
    attempt_repair: bool = True,
) -> TenantSchemaReadiness:
    """Return whether ``schema_name`` has all tenant-model columns Django expects."""
    from django.db import connection

    from apps.schools.tenant_schema_guard import (
        ensure_models_columns,
        missing_tenant_columns,
        run_tenant_column_repairs,
    )

    try:
        from django_tenants.utils import schema_context
    except ImportError:
        # Shared-schema / RLS mode: current connection IS the tenant schema.
        def schema_context(name):  # type: ignore[misc]
            from contextlib import contextmanager

            @contextmanager
            def _noop():
                yield

            return _noop()

    repaired: list[str] = []
    with schema_context(schema_name):
        missing = missing_tenant_columns()
        if attempt_repair and missing:
            run_tenant_column_repairs()
            with connection.schema_editor() as schema_editor:
                added = ensure_models_columns(
                    schema_editor, _models_for_missing(missing)
                )
            repaired.extend(added)
            missing = missing_tenant_columns()

    labels = tuple(sorted({f"{table}.{column}" for _a, _m, table, column in missing}))
    return TenantSchemaReadiness(
        schema_name=schema_name,
        ready=len(labels) == 0,
        missing_labels=labels,
        repaired_labels=tuple(repaired),
        repair_attempted=attempt_repair,
    )


def readiness_for_bundle(
    bundle: Any,
    *,
    attempt_repair: bool = False,
) -> TenantSchemaReadiness | None:
    """Lightweight schema check for a bundle (UI polls use ``attempt_repair=False``)."""
    from .schema_binding import ensure_bundle_schema_name

    schema_name = ensure_bundle_schema_name(bundle)
    if not schema_name:
        return None

    summary = getattr(bundle, "size_summary", None) or {}
    drift = summary.get("tenant_schema_drift")
    if isinstance(drift, dict) and drift.get("missing_columns"):
        return TenantSchemaReadiness(
            schema_name=schema_name,
            ready=False,
            missing_labels=tuple(drift.get("missing_columns") or ()),
            repaired_labels=tuple(drift.get("repaired_columns") or ()),
            repair_attempted=bool(drift.get("repair_attempted")),
        )

    return assess_tenant_schema_readiness(schema_name, attempt_repair=attempt_repair)


def format_schema_drift_reason(readiness: TenantSchemaReadiness) -> str:
    if readiness.ready:
        return ""
    preview = ", ".join(readiness.missing_labels[:8])
    extra = ""
    if len(readiness.missing_labels) > 8:
        extra = f" (+{len(readiness.missing_labels) - 8} more)"
    return (
        "This school's database schema is behind the platform version — missing "
        f"columns: {preview}{extra}. Ask your operator to run tenant migrations "
        "for this school, then use Repair again."
    )


def schema_drift_summary_patch(readiness: TenantSchemaReadiness) -> dict:
    return {
        "error": format_schema_drift_reason(readiness),
        "tenant_schema_drift": {
            "schema_name": readiness.schema_name,
            "missing_columns": list(readiness.missing_labels),
            "repaired_columns": list(readiness.repaired_labels),
            "repair_attempted": readiness.repair_attempted,
        },
    }


def post_apply_step_error(exc: BaseException) -> dict:
    """Structured summary for a best-effort post-apply hook failure."""
    from django.db.utils import ProgrammingError

    detail = str(exc)[:500]
    if isinstance(exc, ProgrammingError) and "does not exist" in detail.lower():
        return {
            "ok": False,
            "error": "tenant_schema_drift",
            "detail": detail,
        }
    return {
        "ok": False,
        "error": "post_apply_step_failed",
        "detail": detail,
    }
