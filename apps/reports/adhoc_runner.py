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
    date_from = params.get('date_from') or definition.date_from
    date_to = params.get('date_to') or definition.date_to
    filters = {**definition.filters, **params.get('filters', {})}
    out_fmt = output_format or definition.output_format
    effective_school_id = school_id_override if school_id_override is not None else definition.school_id

    execution = AdHocReportExecution.objects.create(
        definition=definition,
        executed_by=executed_by,
        parameters_override=params,
        status='RUNNING',
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
        execution.status = 'COMPLETED'
        execution.completed_at = timezone.now()
        execution.save(update_fields=['row_count', 'execution_time_ms', 'status', 'completed_at'])

        if out_fmt == 'CSV':
            buf = io.StringIO()
            writer = csv.DictWriter(buf, fieldnames=headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(row_dicts)
            return (buf.getvalue().encode('utf-8'), None, row_count, None)
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
        execution.status = 'FAILED'
        execution.error_message = str(e)
        execution.completed_at = timezone.now()
        execution.save(update_fields=['status', 'error_message', 'completed_at'])
        return (None, None, 0, str(e))


def _build_queryset(entity_type: str, columns: list, filters: dict, date_from, date_to, school_id, allow_global: bool = False):
    """Build Django queryset and column list from entity_type and filters."""

    if not columns:
        columns = ['id']
    if not school_id and not allow_global:
        raise ValueError("school_id required for tenant-scoped ad-hoc report execution")

    if entity_type == 'STUDENTS':
        from apps.people.models import StudentProfile
        qs = StudentProfile.objects.all().order_by('id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        for key, val in filters.items():
            if key == 'classroom_id':
                qs = qs.filter(classroom_id=val)
            elif key == 'is_active':
                qs = qs.filter(is_active=bool(val))
            elif key == 'academic_year_id':
                qs = qs.filter(academic_year_id=val)
        # Ensure only valid field names
        allowed = {f.name for f in StudentProfile._meta.get_fields()}
        headers = [c for c in columns if c in allowed or c.startswith('classroom__')]
        if not headers:
            headers = ['id']
        return qs, headers

    if entity_type == 'ATTENDANCE':
        from apps.academics.models import Attendance
        qs = Attendance.objects.all().select_related('student', 'classroom').order_by('-date', 'student_id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        for key, val in filters.items():
            if key == 'classroom_id':
                qs = qs.filter(classroom_id=val)
            elif key == 'status':
                qs = qs.filter(status=val)
        allowed = {f.name for f in Attendance._meta.get_fields()}
        headers = [c for c in columns if c in allowed or any(c.startswith(p) for p in ('student__', 'classroom__'))]
        if not headers:
            headers = ['id', 'date', 'status', 'student_id', 'classroom_id']
        return qs, headers

    if entity_type == 'FINANCE':
        from apps.finance.models import Invoice
        qs = Invoice.objects.all().order_by('-created_at')
        if school_id:
            qs = qs.filter(school_id=school_id)
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)
        for key, val in filters.items():
            if hasattr(Invoice, key):
                qs = qs.filter(**{key: val})
        allowed = {f.name for f in Invoice._meta.get_fields()}
        headers = [c for c in columns if c in allowed]
        if not headers:
            headers = ['id', 'student_id', 'total_amount', 'status', 'created_at']
        return qs, headers

    if entity_type == 'ENROLLMENT':
        from apps.people.models import StudentProfile
        qs = StudentProfile.objects.filter(is_active=True).order_by('id')
        if school_id:
            qs = qs.filter(school_id=school_id)
        for key, val in filters.items():
            if key == 'classroom_id':
                qs = qs.filter(classroom_id=val)
            elif key == 'academic_year_id':
                qs = qs.filter(academic_year_id=val)
        allowed = {f.name for f in StudentProfile._meta.get_fields()}
        headers = [c for c in columns if c in allowed or c.startswith('classroom__')]
        if not headers:
            headers = ['id', 'first_name', 'last_name', 'classroom_id']
        return qs, headers

    # CUSTOM / fallback: minimal students list
    from apps.people.models import StudentProfile
    qs = StudentProfile.objects.all().order_by('id')
    if school_id:
        qs = qs.filter(school_id=school_id)
    qs = qs[:1000]
    headers = ['id', 'first_name', 'last_name']
    return qs, headers
