"""
Deterministic analytics bundle seeder (Python mirror of src/database/seeds/analytics-seeder.ts).

Used for demo tenants, staging, and management command — NOT for production tenant truth.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _round_money(value: float | Decimal, places: int = 1) -> float:
    quant = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_UP))


def _sum_money(values: list[float], places: int = 1) -> float:
    return _round_money(sum(values), places)


def _rng(tenant_id: str):
    h = 1779033703
    for ch in tenant_id:
        h = ((h ^ ord(ch)) * 3432918353) & 0xFFFFFFFF
        h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
    state = h

    def next_float() -> float:
        nonlocal state
        state = (state ^ (state >> 16)) * 2246822519 & 0xFFFFFFFF
        state = (state ^ (state >> 13)) * 3266489909 & 0xFFFFFFFF
        state = (state ^ (state >> 16)) & 0xFFFFFFFF
        return state / 4294967296.0

    return next_float


def _is_weekend(d: dt.date) -> bool:
    return d.weekday() >= 5


def _is_break(d: dt.date) -> bool:
    if d.month in (7, 8):
        return True
    if d.month == 12 and d.day >= 18:
        return True
    if d.month == 1 and d.day <= 6:
        return True
    return False


def _is_term_start(d: dt.date) -> bool:
    return (d.month == 9 and d.day <= 14) or (d.month == 1 and 8 <= d.day <= 21)


def seed_tenant_analytics_bundle(
    tenant_id: str,
    *,
    months: int = 9,
    start: dt.date | None = None,
) -> dict[str, Any]:
    start_date = start or dt.date(2025, 9, 1)
    end = start_date + dt.timedelta(days=months * 31)
    rng = _rng(tenant_id)
    timeseries: list[dict[str, Any]] = []
    cursor = start_date
    while cursor < end:
        base_att = 0.88 - (0.22 if _is_weekend(cursor) else 0) - (0.35 if _is_break(cursor) else 0)
        att = _round_money(
            min(99.0, max(35.0, (base_att + (rng() - 0.5) * 0.06) * 100)),
            1,
        )
        base_rev = 4200 + (2800 if _is_term_start(cursor) else 0) - (900 if _is_weekend(cursor) else 0)
        base_rev -= 1100 if _is_break(cursor) else 0
        rev = _round_money(max(250.0, base_rev + (rng() - 0.5) * 400), 1)
        timeseries.append(
            {
                "date": cursor.isoformat(),
                "attendanceRate": att,
                "revenue": rev,
            }
        )
        cursor += dt.timedelta(days=1)

    revenue_total = _sum_money([p["revenue"] for p in timeseries])
    attendance_avg = _round_money(
        sum(p["attendanceRate"] for p in timeseries) / max(len(timeseries), 1),
        1,
    )
    spark_att = [p["attendanceRate"] for p in timeseries[-14:]]
    spark_rev = [p["revenue"] for p in timeseries[-14:]]

    budget_total = _round_money(revenue_total * 1.12, 1)
    weights = [
        ("instruction", "Instruction", 0.42),
        ("operations", "Operations", 0.24),
        ("facilities", "Facilities", 0.18),
        ("technology", "Technology", 0.11),
        ("reserve", "Reserve", 0.05),
    ]
    allocation = []
    for idx, (slug, label, weight) in enumerate(weights):
        allocation.append(
            {
                "id": slug,
                "label": label,
                "value": _round_money(budget_total * weight, 1),
                "dashPattern": "0" if idx % 2 == 0 else "4 3",
            }
        )
    alloc_sum = _sum_money([s["value"] for s in allocation])
    if alloc_sum != budget_total and allocation:
        allocation[0]["value"] = _round_money(allocation[0]["value"] + (budget_total - alloc_sum), 1)

    enrolled = int(820 + rng() * 120)

    def kpi(kid: str, label: str, value: float, formatted: str, spark: list[float]) -> dict:
        delta = _round_money((rng() - 0.35) * 12, 1)
        direction = "up" if delta > 0.4 else "down" if delta < -0.4 else "neutral"
        return {
            "id": kid,
            "label": label,
            "value": value,
            "formattedValue": formatted,
            "deltaPercent": abs(delta),
            "direction": direction,
            "sparkline": spark,
            "helpText": f"{label} for tenant {tenant_id} — seeded deterministic curve.",
        }

    kpis = [
        kpi("attendance", "Attendance rate", attendance_avg, f"{attendance_avg:.1f}%", spark_att),
        kpi("revenue", "Live revenue", revenue_total, f"{revenue_total:,.1f}", spark_rev),
        kpi("enrollment", "Active students", float(enrolled), f"{enrolled}", spark_att),
    ]

    return {
        "tenantId": tenant_id,
        "timeseries": timeseries,
        "kpis": kpis,
        "allocation": allocation,
        "totals": {"revenue": revenue_total, "budget": budget_total},
        "meta": {
            "empty": False,
            "source": "seed",
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "drillDown": {
            "revenue": "/finance/",
            "attendance": "/portal/analytics/",
            "instruction": "/finance/",
        },
    }


def validate_bundle_integrity(bundle: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    series_rev = _sum_money([p["revenue"] for p in bundle.get("timeseries", [])])
    totals_rev = bundle.get("totals", {}).get("revenue")
    if series_rev != totals_rev:
        errors.append(f"revenue series {series_rev} != totals {totals_rev}")
    alloc = _sum_money([s["value"] for s in bundle.get("allocation", [])])
    budget = bundle.get("totals", {}).get("budget")
    if alloc != budget:
        errors.append(f"allocation {alloc} != budget {budget}")
    return len(errors) == 0, errors
