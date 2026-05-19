"""
Build TenantAnalyticsBundle-shaped JSON from live tenant data (school-scoped).
"""

from __future__ import annotations

import datetime as dt
import logging
from decimal import Decimal
from typing import Any

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.analytics.services.analytics_seeder_py import seed_tenant_analytics_bundle

logger = logging.getLogger(__name__)

DEMO_TENANT_SLUGS = frozenset(
    {"marketing-demo", "platform-overview", "platform-meal-ops", "audit-tenant"}
)


def _round_money(value: Decimal | float, places: int = 1) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.1") if places == 1 else Decimal("0.01")))


def _direction(delta: float) -> str:
    if delta > 0.4:
        return "up"
    if delta < -0.4:
        return "down"
    return "neutral"


def _parse_dates(
    from_date: dt.date | None,
    to_date: dt.date | None,
    *,
    default_days: int = 90,
) -> tuple[dt.date, dt.date]:
    end = to_date or timezone.localdate()
    start = from_date or (end - dt.timedelta(days=default_days))
    if start > end:
        start, end = end, start
    return start, end


def build_tenant_overview_bundle(
    *,
    tenant_id: str,
    school=None,
    from_date: dt.date | None = None,
    to_date: dt.date | None = None,
    compare: bool = False,
) -> dict[str, Any]:
    """Return analytics overview JSON for React TenantOverview."""
    if school is None or tenant_id in DEMO_TENANT_SLUGS:
        bundle = seed_tenant_analytics_bundle(tenant_id)
        bundle["meta"]["source"] = "seed-demo"
        return bundle

    start, end = _parse_dates(from_date, to_date)
    span_days = (end - start).days + 1
    prev_end = start - dt.timedelta(days=1)
    prev_start = prev_end - dt.timedelta(days=span_days - 1)

    timeseries = _build_timeseries(school, start, end)
    prev_timeseries = _build_timeseries(school, prev_start, prev_end) if compare else []

    revenue_total = _round_money(sum(p["revenue"] for p in timeseries))
    prev_revenue = _round_money(sum(p["revenue"] for p in prev_timeseries)) if prev_timeseries else 0.0
    attendance_avg = _round_money(
        sum(p["attendanceRate"] for p in timeseries) / max(len(timeseries), 1)
    )

    enrollment = _active_student_count(school)
    allocation = _build_allocation(school, revenue_total)
    budget_total = _round_money(sum(s["value"] for s in allocation))

    spark_att = [p["attendanceRate"] for p in timeseries[-14:]]
    spark_rev = [p["revenue"] for p in timeseries[-14:]]

    rev_delta = 0.0
    if compare and prev_revenue:
        rev_delta = _round_money(((revenue_total - prev_revenue) / prev_revenue) * 100)

    kpis = [
        _kpi(
            "attendance",
            "Attendance rate",
            attendance_avg,
            f"{attendance_avg:.1f}%",
            spark_att,
            school,
            delta_override=None,
        ),
        _kpi(
            "revenue",
            "Live revenue",
            revenue_total,
            f"{revenue_total:,.1f}",
            spark_rev,
            school,
            delta_override=rev_delta if compare else None,
        ),
        _kpi(
            "enrollment",
            "Active students",
            float(enrollment),
            str(enrollment),
            spark_att,
            school,
            delta_override=None,
        ),
    ]

    empty = len(timeseries) == 0 or not any(
        p["revenue"] > 0 or p["attendanceRate"] > 0 for p in timeseries
    )
    return {
        "tenantId": tenant_id,
        "timeseries": timeseries,
        "kpis": kpis,
        "allocation": allocation,
        "totals": {"revenue": revenue_total, "budget": budget_total},
        "meta": {
            "empty": empty,
            "message": (
                "No attendance or payment data in this date range."
                if empty
                else ""
            ),
            "source": "live",
            "compare": compare,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "generatedAt": timezone.now().isoformat(),
        },
        "drillDown": {
            "revenue": "/finance/",
            "attendance": "/portal/analytics/",
            "instruction": "/finance/invoices/",
            "operations": "/finance/payments/",
            "facilities": "/schoolops/",
            "technology": "/portal/analytics/",
            "reserve": "/finance/",
        },
    }


def _kpi(
    kid: str,
    label: str,
    value: float,
    formatted: str,
    sparkline: list[float],
    school,
    *,
    delta_override: float | None,
) -> dict[str, Any]:
    delta = delta_override if delta_override is not None else 0.0
    return {
        "id": kid,
        "label": label,
        "value": value,
        "formattedValue": formatted,
        "deltaPercent": abs(delta),
        "direction": _direction(delta),
        "sparkline": sparkline,
        "helpText": f"{label} for {getattr(school, 'name', 'tenant')} — live aggregates.",
    }


def _active_student_count(school) -> int:
    try:
        from apps.people.models import StudentProfile

        return (
            StudentProfile.objects.filter(school=school, is_active=True)  # type: ignore[attr-defined]
            .count()
        )
    except Exception:
        try:
            from apps.people.models import StudentProfile

            return StudentProfile.objects.filter(school_id=school.pk).count()
        except Exception as exc:
            logger.debug("student count fallback: %s", exc)
            return 0


def _build_timeseries(school, start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    from apps.academics.models import Attendance
    from apps.finance.models import Payment

    att_by_day: dict[dt.date, dict[str, int]] = {}
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    att_qs = Attendance.objects.filter(school=school, date__gte=start, date__lte=end)
    for row in att_qs.values("date").annotate(
        total=Count("id"),
        present=Count("id", filter=Q(status__in=["present", "late", "excused"])),
    ):
        att_by_day[row["date"]] = {"total": row["total"], "present": row["present"]}

    rev_by_day: dict[dt.date, Decimal] = {}
    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
    pay_qs = (
        Payment.objects.filter(school=school, paid_at__date__gte=start, paid_at__date__lte=end)
        .annotate(day=TruncDate("paid_at"))
        .values("day")
        .annotate(total=Sum("amount"))
    )
    for row in pay_qs:
        if row["day"]:
            rev_by_day[row["day"]] = row["total"] or Decimal("0")

    points: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        att = att_by_day.get(cursor, {"total": 0, "present": 0})
        rate = 0.0
        if att["total"]:
            rate = _round_money((att["present"] / att["total"]) * 100)
        rev = _round_money(float(rev_by_day.get(cursor, Decimal("0"))))
        points.append(
            {
                "date": cursor.isoformat(),
                "attendanceRate": rate,
                "revenue": rev,
            }
        )
        cursor += dt.timedelta(days=1)
    return points


def _build_allocation(school, revenue_total: float) -> list[dict[str, Any]]:
    from apps.finance.models import Payment

    labels = [
        ("instruction", "Instruction", "tuition"),
        ("operations", "Operations", "cash"),
        ("facilities", "Facilities", "bank"),
        ("technology", "Technology", "mobile_money"),
        ("reserve", "Reserve", "other"),
    ]
    method_totals: dict[str, Decimal] = {}
    try:
        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        rows = (
            Payment.objects.filter(school=school)
            .values("method")
            .annotate(total=Sum("amount"))
        )
        for row in rows:
            method_totals[row["method"] or "other"] = row["total"] or Decimal("0")
    except Exception as exc:
        logger.debug("allocation query: %s", exc)

    total_dec = sum(method_totals.values(), Decimal("0"))
    if total_dec <= 0:
        budget = revenue_total * 1.12 if revenue_total else 1.0
        weights = [0.42, 0.24, 0.18, 0.11, 0.05]
        return [
            {
                "id": labels[i][0],
                "label": labels[i][1],
                "value": _round_money(budget * weights[i]),
                "dashPattern": "0" if i % 2 == 0 else "4 3",
            }
            for i in range(len(labels))
        ]

    budget = float(total_dec)
    slices = []
    for idx, (slug, label, _method_key) in enumerate(labels):
        key = _method_key if _method_key in method_totals else "other"
        val = float(method_totals.get(key, Decimal("0")))
        if val <= 0:
            val = budget * [0.42, 0.24, 0.18, 0.11, 0.05][idx]
        slices.append(
            {
                "id": slug,
                "label": label,
                "value": _round_money(val),
                "dashPattern": "0" if idx % 2 == 0 else "4 3",
            }
        )
    return slices
