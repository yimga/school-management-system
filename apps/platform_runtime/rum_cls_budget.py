"""RUM CLS budget verifier.

12-pillar audit P10 follow-up. Lighthouse CI gates the **lab** CLS
budget (P1). RUM data measures the **field** CLS as users actually
experience it. A page can pass Lighthouse but regress in the field
when slow networks delay LCP / images load late and shift content.

This module computes the p75 CLS (Web Vitals "good" threshold) per
URL pattern from the RUM ingest store and asserts none exceed the
budget. Backed by the same cache the ingest writes to, so the
verifier is read-only.

Operator wiring:
  * RUM ingest store key prefix: ``rum_cls_samples:{pattern}`` →
    list of CLS values (floats) bounded by RUM_INGEST_MAX_SAMPLES.
  * Pattern resolution: caller passes the URL set explicitly so the
    verifier doesn't have to introspect URLconf.

Today the cache layer used by RUM is in-memory (see
``apps/platform_runtime/views_rum.py``). The verifier returns the
empty-budget report when there are no samples — operators run this
once a meaningful sample stream exists (post-pilot launch).
"""

from __future__ import annotations

from statistics import quantiles
from typing import Iterable

# Web Vitals "good" CLS threshold (web.dev).
CLS_GOOD_BUDGET = 0.1


def compute_p75(samples: Iterable[float]) -> float | None:
    """Return the 75th-percentile of a sample iterable, or None.

    p75 is the Web Vitals canonical reporting metric for field CLS.
    With < 4 samples we return None (insufficient data); with 4-19
    samples we use the simple linear-interpolation quantile.
    """
    values = sorted(float(v) for v in samples if isinstance(v, (int, float)))
    if len(values) < 4:
        return None
    # quantiles(n=4) gives Q1/Q2/Q3 -> Q3 is p75.
    return float(quantiles(values, n=4)[2])


def evaluate(pattern_samples: dict[str, list[float]], *, budget: float = CLS_GOOD_BUDGET) -> dict:
    """Evaluate every (pattern -> samples) entry against the budget.

    Returns a structured payload with per-pattern p75 and a list of
    breaches (p75 > budget). Empty or insufficient sample sets are
    reported as ``insufficient_samples`` and do not count as breaches.
    """
    rows = []
    breaches = []
    insufficient = []
    for pattern, samples in pattern_samples.items():
        p75 = compute_p75(samples)
        row = {
            "pattern": pattern,
            "sample_count": len(list(samples)),
            "p75": p75,
            "budget": budget,
        }
        if p75 is None:
            insufficient.append(pattern)
        elif p75 > budget:
            row["breach"] = True
            breaches.append(row)
        rows.append(row)
    return {
        "budget": budget,
        "rows": rows,
        "breach_count": len(breaches),
        "breaches": breaches,
        "insufficient_samples": insufficient,
    }


__all__ = ["CLS_GOOD_BUDGET", "compute_p75", "evaluate"]
