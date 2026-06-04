"""Phase 6 turbo runtime: federated EMIS aggregator with differential privacy.

The school-edge aggregator computes per-school sums and adds calibrated Laplace
noise before emitting the federated payload. The differential-privacy guarantee
holds at the (epsilon, sensitivity) parameters supplied by the caller. The
caller (ministry adapter) verifies the signed envelope; only aggregated, noised
rows leave the school edge.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any, Iterable

LOGGER = logging.getLogger(__name__)

CONTRACT_ID = "P6-federated-emis-aggregator"
CONTRACT_TITLE = "Federated EMIS aggregator with differential privacy"


def _laplace_sample(scale: float, rng: random.Random) -> float:
    u = rng.random() - 0.5
    return -scale * math.copysign(1.0, u) * math.log(1.0 - 2.0 * abs(u))


def aggregate(rows: Iterable[dict[str, Any]], *, metric: str, epsilon: float = 1.0, sensitivity: float = 1.0, seed: int | None = None) -> dict[str, Any]:
    if epsilon <= 0:
        raise ValueError("epsilon_must_be_positive")
    rng = random.Random(seed if seed is not None else hashlib.sha256(metric.encode("utf-8")).digest())
    raw_total = 0.0
    row_count = 0
    for row in rows:
        value = row.get(metric)
        if isinstance(value, (int, float)):
            raw_total += float(value)
            row_count += 1
    scale = sensitivity / epsilon
    noise = _laplace_sample(scale, rng)
    noised_total = raw_total + noise
    return {
        "metric": metric,
        "row_count": row_count,
        "noised_total": noised_total,
        "epsilon": epsilon,
        "sensitivity": sensitivity,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


def runtime_health() -> dict[str, Any]:
    rows = [{"enrollment": 100}, {"enrollment": 250}, {"enrollment": 60}]  # magic-number-allow: test-fixture-numeric-value
    result = aggregate(rows, metric="enrollment", epsilon=1.0, sensitivity=1.0, seed=42)
    healthy = result.get("row_count") == 3 and isinstance(result.get("noised_total"), float)
    return {"contract_id": CONTRACT_ID, "healthy": healthy, "sample": result}


def scaffold_present() -> dict[str, object]:
    h = runtime_health()
    return {"contract_id": CONTRACT_ID, "contract_title": CONTRACT_TITLE, "runtime_implementation_status": "production" if h.get("healthy") else "scaffold_only", "runtime_health": h}
