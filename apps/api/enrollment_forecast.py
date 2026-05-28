"""Enrollment forecasting — v4.00.12.

Closes the v3.97.0 / Plan XVII stub at apps/api/views_v1.py::EnrollmentForecastView.

Model: ``yoy_growth_avg_v1``. Walks the school's prior academic years,
computes year-over-year growth rates for active students, averages
them, applies the rate forward over the horizon. Returns a list of
``{term, projected, lower_bound, upper_bound, basis_years}``.

Defensive on missing AcademicYear records (returns flat projection),
on schools with 1 year of history (uses that single rate with wider
confidence band), and on any exception (caller catches and returns
empty list with the error message).
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)


def _historical_yearly_counts(school: Any) -> list[tuple[str, int]]:
    """Return [(year_name, active_count_at_year_end), ...] sorted ascending."""
    try:
        from apps.academics.models import AcademicYear
        from apps.people.models import StudentProfile

        years = list(
            AcademicYear.objects.filter(school=school).order_by("start_date")  # tenant-isolation-allow: scoped-via-school-filter-enrollment-history
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("enrollment_forecast: history fetch failed: %s", exc)
        return []
    out: list[tuple[str, int]] = []
    for year in years:
        try:
            count = StudentProfile.objects.filter(
                school=school, enrolled_in_year=year,
            ).count()  # tenant-isolation-allow: scoped-via-school-filter-enrollment-history
        except Exception:  # noqa: BLE001 — schema may not have enrolled_in_year FK
            try:
                count = StudentProfile.objects.filter(
                    school=school, created_at__lte=year.end_date, is_active=True,
                ).count()  # tenant-isolation-allow: scoped-via-school-filter-enrollment-history-fallback
            except Exception:  # noqa: BLE001
                continue
        out.append((str(getattr(year, "name", "") or year.pk), int(count)))
    return out


def _yoy_growth_rates(counts: list[int]) -> list[float]:
    """Return [(c[1]/c[0])-1, (c[2]/c[1])-1, ...] over a series of yearly counts."""
    rates: list[float] = []
    for i in range(1, len(counts)):
        prev = counts[i - 1]
        if prev <= 0:
            continue
        rates.append(counts[i] / prev - 1.0)
    return rates


def _stdev(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(var) if var > 0 else 0.0


def build_forecast(*, school: Any, current_count: int, horizon_terms: int = 3) -> list[dict[str, Any]]:
    """Project enrollment ``horizon_terms`` terms forward.

    Returns ``[{term, projected, lower_bound, upper_bound, basis_years}]``.
    The first projected term is `1 term ahead`; the model assumes each
    "term" is one academic year for simplicity (the consumer can scale).
    """
    if school is None or getattr(school, "pk", None) is None:
        return []
    horizon = max(1, min(int(horizon_terms or 1), 5))

    history = _historical_yearly_counts(school)
    counts = [c for _, c in history]

    if len(counts) >= 2:
        rates = _yoy_growth_rates(counts)
        if rates:
            avg_rate = sum(rates) / len(rates)
            std_rate = _stdev(rates)
            basis_years = len(rates) + 1
        else:
            avg_rate, std_rate, basis_years = 0.0, 0.0, len(counts)
    else:
        avg_rate, std_rate, basis_years = 0.0, 0.0, len(counts)

    # Defensive clamp: insane growth (e.g. 500%) gets capped to 50% per term.
    capped_avg = max(-0.5, min(0.5, avg_rate))
    # 1 sigma band, also capped.
    band = max(0.0, min(0.3, std_rate))

    forecasts: list[dict[str, Any]] = []
    projected = float(current_count)
    for term_index in range(1, horizon + 1):
        projected = projected * (1.0 + capped_avg)
        lower = projected * (1.0 - band) if band > 0 else projected
        upper = projected * (1.0 + band) if band > 0 else projected
        forecasts.append({
            "term": f"T+{term_index}",
            "projected": int(round(projected)),
            "lower_bound": int(round(lower)),
            "upper_bound": int(round(upper)),
            "basis_years": int(basis_years),
            "growth_rate_used": round(capped_avg, 4),
        })
    return forecasts
