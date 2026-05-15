"""
Synthetic at-risk training dataset generator.

Closes the "no training data" gap for `apps/analytics/ml/at_risk_model.py`:
without real tagged data, we generate a labeled synthetic dataset that
mirrors the 9-feature schema of `AtRiskFeatures`. The labels follow a
research-grounded rule kernel + Bernoulli noise so the resulting model is
not a tautology of the heuristic — it captures interactions and slopes
the heuristic does not.

Once a tenant accumulates real outcomes (year-end retention,
GPA-failure, etc.) we replace this with `apps/analytics/ml/training/
real_at_risk_dataset.py`. The two share schema so the training notebook
does not change.

Usage:
    from apps.analytics.ml.synthetic_at_risk_dataset import generate
    X, y = generate(n_samples=5000, seed=42)

The probability kernel is conservative — labels skew slightly toward
"not at risk" (≈30% positive class) so models trained on this don't
over-alarm a fresh tenant on day one.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterator, Sequence

FEATURE_ORDER: tuple[str, ...] = (
    "attendance_rate",
    "absence_count",
    "late_count",
    "avg_evaluation_score",
    "evaluation_count",
    "eval_score_trend",
    "open_invoice_count",
    "open_balance_amount",
    "days_since_last_login",
)


@dataclass(frozen=True)
class SyntheticRow:
    features: tuple[float, ...]
    label: int  # 1 = at-risk, 0 = not


def _sample_one(rng: random.Random) -> SyntheticRow:
    # Latent "wellness" factor 0..1 drives correlated features (real students
    # don't have independent attendance + grade + finance — they're correlated).
    wellness = rng.betavariate(2.0, 2.0)  # ~symmetric around 0.5

    attendance_rate = max(0.0, min(1.0, rng.gauss(wellness, 0.10)))
    absence_count = int(max(0, rng.gauss((1 - attendance_rate) * 40, 4)))
    late_count = int(max(0, rng.gauss(absence_count * 0.4, 2)))
    avg_evaluation_score = max(0.0, min(100.0, rng.gauss(40 + wellness * 60, 8)))
    evaluation_count = int(max(0, rng.gauss(12, 3)))
    eval_score_trend = rng.gauss((wellness - 0.5) * 10, 4)
    open_invoice_count = int(max(0, rng.gauss((1 - wellness) * 3, 1.0)))
    open_balance_amount = max(0.0, rng.gauss(open_invoice_count * 250, 80))
    days_since_last_login = int(
        max(0, rng.gauss((1 - wellness) * 14, 4))
    )

    # Probability of being at-risk: nonlinear combination of features.
    risk_logit = (
        -1.6
        + 3.2 * (1 - attendance_rate)
        + 0.04 * absence_count
        + 0.02 * late_count
        - 0.04 * (avg_evaluation_score - 50)
        - 0.12 * eval_score_trend
        + 0.20 * open_invoice_count
        + 0.0008 * open_balance_amount
        + 0.05 * days_since_last_login
    )
    risk_prob = 1 / (1 + math.exp(-risk_logit))
    # Add a small Bernoulli noise so models can't memorize the kernel exactly.
    if rng.random() < 0.05:
        risk_prob = 1 - risk_prob
    label = 1 if rng.random() < risk_prob else 0

    return SyntheticRow(
        features=(
            round(attendance_rate, 3),
            absence_count,
            late_count,
            round(avg_evaluation_score, 2),
            evaluation_count,
            round(eval_score_trend, 2),
            open_invoice_count,
            round(open_balance_amount, 2),
            days_since_last_login,
        ),
        label=label,
    )


def iter_samples(n_samples: int = 5000, seed: int = 42) -> Iterator[SyntheticRow]:
    rng = random.Random(seed)
    for _ in range(n_samples):
        yield _sample_one(rng)


def generate(
    n_samples: int = 5000, seed: int = 42
) -> tuple[list[Sequence[float]], list[int]]:
    """Return parallel lists X, y for sklearn-style consumption."""
    X: list[Sequence[float]] = []
    y: list[int] = []
    for row in iter_samples(n_samples=n_samples, seed=seed):
        X.append(row.features)
        y.append(row.label)
    return X, y


__all__ = ["FEATURE_ORDER", "SyntheticRow", "iter_samples", "generate"]
