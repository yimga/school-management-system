#!/usr/bin/env python3
"""Grade-prediction model training entry point (Wave 7).

Reads training data from a labeled CSV (exported by an operator from
the `GradePredictionLabel` table joined to feature-history per scope)
and fits a regression model. Writes a joblib bundle matching the same
shape as `train_at_risk.py` so the registry / loader / shadow code
work without special-casing.

CSV schema:
    prior_mean_score, mid_term_avg, mid_term_count, attendance_rate,
    absence_count, eval_trend, incident_count, days_in_term_so_far, label

Where `label` is the final end-of-term grade (0-100 float).

Soft-fails on missing sklearn/joblib — pipeline falls back to heuristic.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("apps.analytics.ml.train_grade_prediction")

_FEATURE_ORDER = (
    "prior_mean_score",
    "mid_term_avg",
    "mid_term_count",
    "attendance_rate",
    "absence_count",
    "eval_trend",
    "incident_count",
    "days_in_term_so_far",
)
_DEFAULT_OUT = "var/grade_prediction_model.joblib"
_DEFAULT_TEST_FRACTION = 0.2


def _read_csv(path: str) -> tuple[list[list[float]], list[float]]:
    X: list[list[float]] = []
    y: list[float] = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                X.append([float(row[col]) for col in _FEATURE_ORDER])
                y.append(float(row["label"]))
            except (KeyError, ValueError) as exc:
                logger.warning("skipping malformed row: %s", exc)
                continue
    return X, y


def _train(X: list[list[float]], y: list[float], *, test_frac: float):
    """Fit a GradientBoostingRegressor with a stratified-ish train/test split.

    Regression doesn't stratify; we just shuffle deterministically.
    """
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_frac, random_state=42,
    )
    model = GradientBoostingRegressor(
        n_estimators=150, max_depth=3, learning_rate=0.05, random_state=42,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mae = float(mean_absolute_error(y_test, y_pred))
    rmse = float(math.sqrt(sum((p - a) ** 2 for p, a in zip(y_pred, y_test)) / len(y_pred)))
    r2 = float(r2_score(y_test, y_pred))
    return model, {"mae": mae, "rmse": rmse, "r2": r2, "n_test": len(y_test)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train grade-prediction model")
    parser.add_argument("--csv", required=True, help="Labeled training CSV.")
    parser.add_argument("--out", default=_DEFAULT_OUT)
    parser.add_argument(
        "--test-frac", type=float, default=_DEFAULT_TEST_FRACTION,
    )
    parser.add_argument(
        "--model-version", default="",
        help="Stable identifier; defaults to grade_v_<UTC timestamp>.",
    )
    args = parser.parse_args(argv)

    try:
        import joblib
    except ImportError:
        logger.error("joblib/scikit-learn not installed; cannot train.")
        return 1

    X, y = _read_csv(args.csv)
    if len(X) < 20:
        logger.error(
            "Refusing to train on %d rows (minimum 20). Collect more labels.",
            len(X),
        )
        return 2
    model, metrics = _train(X, y, test_frac=args.test_frac)
    trained_at = datetime.now(dt_timezone.utc).isoformat()
    version = (
        args.model_version
        or f"grade_v_{datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )
    bundle = {
        "model": model,
        "feature_order": list(_FEATURE_ORDER),
        "model_version": version,
        "trained_at": trained_at,
        "training_row_count": len(X),
        "holdout_metrics": metrics,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, out_path)
    print(json.dumps({  # noqa: T201 -- intentional script output
        "wrote": str(out_path),
        "version": version,
        "metrics": metrics,
        "n_total": len(X),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
