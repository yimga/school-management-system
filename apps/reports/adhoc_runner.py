"""
Phase 9: Ad-hoc report runner.
Builds queryset from AdHocReportDefinition (entity_type, columns, filters, date range)
and returns CSV bytes or JSON-serializable list of dicts.
"""

from __future__ import annotations

import csv
import io
import time
from datetime import datetime
from typing import Optional

from django.db import DatabaseError, IntegrityError
from django.utils import timezone
from django.core.exceptions import ValidationError

from apps.platform_runtime.structured_logging import log_exception_with_context

from .bi_models import AdHocReportDefinition, AdHocReportExecution

# Expected failures during ad-hoc report run (queryset build, serialize, save, encode).
_REPORT_RUN_ERRORS = (
    DatabaseError,
    IntegrityError,
    ValidationError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
    OSError,
    ImportError,
)


def run_adhoc_report(
    definition: AdHocReportDefinition,
    executed_by,
    parameters_override: Optional[dict] = None,
    output_format: Optional[str] = None,
    school_id_override=None,
    allow_global: bool = False,
) -> tuple[Optional[bytes], Optional[list], int, Optional[str]]:
    """
    Run an ad-hoc report. Returns (csv_bytes or None, json_rows or None, row_count, error_message).
    If output_format is 'CSV', first element is CSV bytes and second is None.
    If output_format is 'JSON', first is None and second is list of dicts.
    """
    params = dict(parameters_override or {})
    date_from = params.get("date_from") or definition.date_from
    date_to = params.get("date_to") or definition.date_to
    filters = {**definition.filters, **params.get("filters", {})}
    out_fmt = output_format or definition.output_format
    effective_school_id = (
        school_id_override if school_id_override is not None else definition.school_id
    )

    execution = AdHocReportExecution.objects.create(
        definition=definition,
        executed_by=executed_by,
        parameters_override=params,
        status="RUNNING",
        started_at=timezone.now(),
    )
    start = time.perf_counter()
    try:
        qs, headers = _build_queryset(
            definition.entity_type,
            definition.columns,
            filters,
            date_from,
            date_to,
            effective_school_id,
            allow_global=allow_global,
        )
        row_dicts = list(qs.values(*headers) if headers else [])
        for d in row_dicts:
            for k, v in list(d.items()):
                if isinstance(v, datetime):
                    d[k] = v.isoformat()

        row_count = len(row_dicts)
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        execution.row_count = row_count
        execution.execution_time_ms = elapsed_ms
        execution.status = "COMPLETED"
        execution.completed_at = timezone.now()
        execution.save(
            update_fields=["row_count", "execution_time_ms", "status", "completed_at"]
        )

        if out_fmt == "CSV":
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(row_dicts)
            return (buf.getvalue().encode("utf-8"), None, row_count, None)
        return (None, row_dicts, row_count, None)
    except _REPORT_RUN_ERRORS as e:
        log_exception_with_context(
            "adhoc_report run failed",
            school_id=getattr(definition, "school_id", None),
            extra={
                "definition_id": getattr(definition, "id", None),
                "execution_id": execution.id,
                "entity_type": getattr(definition, "entity_type", None),
            },
            exc_info=True,
        )
        execution.status = "FAILED"
        execution.error_message = str(e)
        execution.completed_at = timezone.now()
        execution.save(update_fields=["status", "error_message", "completed_at"])
        return (None, None, 0, str(e))


def _build_queryset(
    entity_type: str,
    columns: list,
    filters: dict,
    date_from,
    date_to,
    school_id,
    allow_global: bool = False,
):
    """Build Django queryset and column list from entity_type and filters."""

    from apps.reports.report_entity_registry import (
        queryset_for_code,
        resolve_entity,
    )

    if not columns:
        columns = ["id"]
    if not school_id and not allow_global:
        raise ValueError("school_id required for tenant-scoped ad-hoc report execution")

    filters = dict(filters or {})
    raw_type = str(entity_type or "").strip()
    lookup = raw_type
    if raw_type.upper() == "CUSTOM":
        lookup = str(
            filters.get("entity_code")
            or filters.get("catalog_code")
            or filters.get("model_label")
            or ""
        ).strip()
        if not lookup:
            raise ValueError(
                "CUSTOM reports require filters.entity_code (catalog code) "
                "or filters.model_label; unknown entities fail closed"
            )
    if raw_type.upper() == "ENROLLMENT":
        filters.setdefault("is_active", True)

    entity = resolve_entity(lookup)
    if entity is None:
        raise ValueError(f"unknown report entity {lookup!r}")
    return queryset_for_code(
        lookup,
        columns=columns,
        filters=filters,
        date_from=date_from,
        date_to=date_to,
        school_id=school_id,
        allow_global=allow_global,
    )
