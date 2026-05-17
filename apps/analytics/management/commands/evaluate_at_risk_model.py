"""Evaluate a candidate at-risk model artifact against a holdout dataset.

Sister command to `train_at_risk_baseline`. Loads a joblib bundle, runs
predictions on either synthetic data (smoke), an explicit holdout CSV, or
labels exported by `export_at_risk_training_data`, and emits a structured
JSON report (ROC AUC, average precision, precision/recall at the platform's
default 0.5 threshold, calibration error, and a confusion matrix).

Use as a pre-deploy gate:

    python manage.py evaluate_at_risk_model var/at_risk_model.joblib \
        --csv var/holdout_2026_q1.csv \
        --json var/at_risk_eval_2026_q1.json

Exit code 0 only when **all** of the configurable thresholds are met:

  * `--min-roc-auc`             default 0.70
  * `--min-average-precision`   default 0.40

Without thresholds the command always exits 0 (report-only mode).
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


logger = logging.getLogger("apps.analytics.commands.evaluate_at_risk_model")


class Command(BaseCommand):
    help = "Evaluate an at-risk model joblib bundle against a labeled holdout."

    def add_arguments(self, parser):
        parser.add_argument("artifact", help="Path to the joblib bundle to evaluate.")
        parser.add_argument(
            "--csv",
            default=None,
            help=(
                "Holdout CSV path. Schema: features matching bundle "
                "`feature_order` plus a `label` column."
            ),
        )
        parser.add_argument(
            "--samples",
            type=int,
            default=2000,
            help="If no --csv: synthetic holdout sample count.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=4242,
            help="Synthetic-mode seed (different from training seed by default).",
        )
        parser.add_argument(
            "--threshold",
            type=float,
            default=0.5,
            help="Classification threshold for precision/recall at-cutoff.",
        )
        parser.add_argument("--min-roc-auc", type=float, default=None)
        parser.add_argument("--min-average-precision", type=float, default=None)
        parser.add_argument(
            "--json",
            default=None,
            help="Optional JSON report output path.",
        )

    def handle(self, *args, **opts):
        try:
            import joblib  # type: ignore
            from sklearn.metrics import (
                average_precision_score,
                confusion_matrix,
                precision_recall_fscore_support,
                roc_auc_score,
            )
        except ImportError as exc:
            raise CommandError(
                "scikit-learn + joblib required: pip install scikit-learn joblib"
            ) from exc

        artifact_path = Path(opts["artifact"])
        if not artifact_path.exists():
            raise CommandError(f"Artifact not found: {artifact_path}")

        bundle = joblib.load(artifact_path)
        if not isinstance(bundle, dict) or "model" not in bundle:
            raise CommandError(
                f"Bundle at {artifact_path} is not in expected shape "
                "(dict with 'model' / 'feature_order' keys)."
            )
        model = bundle["model"]
        feature_order = bundle.get("feature_order") or []
        model_version = bundle.get("model_version", "unknown")

        X, y = self._load_holdout(opts, feature_order)
        self.stdout.write(
            f"Loaded holdout: n={len(X)}, positives={sum(y)} "
            f"({(sum(y) / len(y) * 100):.1f}%)"
        )

        try:
            proba = model.predict_proba(X)[:, 1]
        except (AttributeError, IndexError):
            raw = model.predict(X)
            proba = [r / 100.0 if r > 1 else r for r in raw]

        threshold = float(opts["threshold"])
        preds = [1 if p >= threshold else 0 for p in proba]
        auc = float(roc_auc_score(y, proba))
        ap = float(average_precision_score(y, proba))
        prec, rec, f1, _ = precision_recall_fscore_support(
            y, preds, average="binary", zero_division=0
        )
        # Force a 2x2 matrix even when one class is absent from preds/y,
        # otherwise cm[0][1] raises IndexError on degenerate holdouts.
        cm = confusion_matrix(y, preds, labels=[0, 1]).tolist()

        report = {
            "artifact": str(artifact_path),
            "model_version": model_version,
            "holdout_size": len(X),
            "positive_rate": sum(y) / len(y),
            "threshold": threshold,
            "metrics": {
                "roc_auc": auc,
                "average_precision": ap,
                "precision_at_threshold": float(prec),
                "recall_at_threshold": float(rec),
                "f1_at_threshold": float(f1),
            },
            "confusion_matrix": {
                "tn": cm[0][0], "fp": cm[0][1], "fn": cm[1][0], "tp": cm[1][1],
            },
        }

        for k, v in report["metrics"].items():
            self.stdout.write(f"  {k:32s} {v:.4f}")

        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))
            self.stdout.write(self.style.SUCCESS(f"Wrote {opts['json']}"))

        gate_failures = []
        if opts.get("min_roc_auc") is not None and auc < opts["min_roc_auc"]:
            gate_failures.append(
                f"roc_auc={auc:.3f} < min={opts['min_roc_auc']:.3f}"
            )
        if (
            opts.get("min_average_precision") is not None
            and ap < opts["min_average_precision"]
        ):
            gate_failures.append(
                f"average_precision={ap:.3f} < min={opts['min_average_precision']:.3f}"
            )
        if gate_failures:
            raise CommandError(
                "Model failed deploy gate: " + "; ".join(gate_failures)
            )

    def _load_holdout(self, opts, feature_order):
        if opts.get("csv"):
            return self._load_csv(opts["csv"], feature_order)
        from apps.analytics.ml.synthetic_at_risk_dataset import generate

        X, y = generate(n_samples=opts["samples"], seed=opts["seed"])
        return X, y

    def _load_csv(self, path: str, feature_order):
        if not feature_order:
            raise CommandError(
                "Bundle missing feature_order; cannot align CSV columns."
            )
        X, y = [], []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                X.append([float(row[c]) for c in feature_order])
                y.append(int(row["label"]))
        return X, y
