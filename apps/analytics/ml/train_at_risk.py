#!/usr/bin/env python3
"""
At-risk model training entry point.

Reads training data either from the synthetic generator or from a real
labeled CSV, fits a calibrated classifier, evaluates on a holdout, and
writes the joblib artifact to `settings.AT_RISK_MODEL_PATH` (default
`var/at_risk_model.joblib`).

Usage:
  python apps/analytics/ml/train_at_risk.py                    # synthetic, n=5000
  python apps/analytics/ml/train_at_risk.py --samples 20000
  python apps/analytics/ml/train_at_risk.py --csv real.csv
  python apps/analytics/ml/train_at_risk.py --out var/model.joblib

CSV schema must match `synthetic_at_risk_dataset.FEATURE_ORDER`
followed by a `label` column.

Soft-fails on missing sklearn/joblib — the calling pipeline keeps using
the heuristic baseline in `apps.analytics.ml.at_risk_model`.
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[3]

logger = logging.getLogger("apps.analytics.ml.train_at_risk")

# Local import — no Django import on purpose. This script is run with the
# project venv but does not need ORM access. Keeps the artifact reproducible
# from a clean checkout.
sys.path.insert(0, str(ROOT))
from apps.analytics.ml.synthetic_at_risk_dataset import (  # noqa: E402
    FEATURE_ORDER,
    generate,
)


def _load_csv(path: str) -> tuple[list[Sequence[float]], list[int]]:
    X: list[Sequence[float]] = []
    y: list[int] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            X.append([float(row[col]) for col in FEATURE_ORDER])
            y.append(int(row["label"]))
    return X, y


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--samples", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--csv", type=str, default=None, help="Real labeled CSV instead of synthetic.")
    p.add_argument("--out", type=str, default=None, help="Output joblib path.")
    p.add_argument("--no-write", action="store_true", help="Skip writing the artifact.")
    args = p.parse_args(argv)

    try:
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.metrics import (
            average_precision_score,
            classification_report,
            roc_auc_score,
        )
        from sklearn.model_selection import train_test_split
        import joblib  # type: ignore
    except ImportError as exc:
        logger.error("training prerequisites missing — install scikit-learn + joblib: %s", exc)
        logger.error("  pip install scikit-learn joblib")
        return 2

    if args.csv:
        logger.info("Loading real labeled data from %s", args.csv)
        X, y = _load_csv(args.csv)
    else:
        logger.info("Generating synthetic dataset (n=%s, seed=%s)", args.samples, args.seed)
        X, y = generate(n_samples=args.samples, seed=args.seed)
    logger.info("  X shape: (%s, %s) features=%s", len(X), len(X[0]), list(FEATURE_ORDER))
    logger.info("  Positive class rate: %.1f%%", (sum(y) / len(y)) * 100)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=args.seed, stratify=y
    )

    base = GradientBoostingClassifier(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.08,
        random_state=args.seed,
    )
    # Calibrate so predict_proba is well-calibrated and the platform's 0..100
    # at-risk score has meaning (prob * 100), not just rank ordering.
    clf = CalibratedClassifierCV(base, method="isotonic", cv=3)
    clf.fit(X_train, y_train)

    proba = clf.predict_proba(X_test)[:, 1]
    preds = (proba >= 0.5).astype(int)
    auc = roc_auc_score(y_test, proba)
    ap = average_precision_score(y_test, proba)

    logger.info("Holdout metrics:")
    logger.info("  ROC AUC:        %.3f", auc)
    logger.info("  Average prec.:  %.3f", ap)
    logger.info("%s", classification_report(y_test, preds, digits=3))

    if args.no_write:
        logger.info("(--no-write set; skipping artifact write)")
        return 0

    out_path = args.out or os.environ.get("AT_RISK_MODEL_PATH") or "var/at_risk_model.joblib"
    out_dir = Path(out_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": clf,
            "feature_order": list(FEATURE_ORDER),
            "training": {
                "source": "synthetic" if not args.csv else args.csv,
                "n_samples": len(X),
                "positive_rate": sum(y) / len(y),
                "roc_auc": auc,
                "average_precision": ap,
                "seed": args.seed,
            },
            "model_version": "at_risk_v1_synthetic" if not args.csv else "at_risk_v1_real",
        },
        out_path,
    )
    logger.info("Wrote %s", out_path)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
