"""Regression-style calibration check for grade-prediction.

For regression models, calibration ≠ classification ECE. We bin
predictions, then per bin compute MAE between predictions and actuals.
A well-calibrated regressor has roughly uniform per-bin MAE.

Output:
    overall MAE / RMSE
    per-bin (count, avg_pred, avg_actual, bin_mae, bin_bias)
    bias = avg_pred - avg_actual; persistent positive bias = optimistic
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import GradePrediction, GradePredictionLabel
from apps.schools.models import School

_BIN_COUNT = 10
_BIN_WIDTH = 10


def _bin(value: float) -> int:
    if value >= _BIN_COUNT * _BIN_WIDTH:
        return _BIN_COUNT - 1
    if value <= 0:
        return 0
    return min(int(value // _BIN_WIDTH), _BIN_COUNT - 1)


class Command(BaseCommand):
    help = "Per-bin MAE / bias for grade-prediction (regression calibration)."

    def add_arguments(self, parser):
        parser.add_argument("--school", default=None)
        parser.add_argument("--academic-year", default=None)
        parser.add_argument("--term", default=None)
        parser.add_argument(
            "--min-samples-per-bin", type=int, default=5,
        )
        parser.add_argument("--max-overall-mae", type=float, default=None)
        parser.add_argument("--json", default=None)

    def handle(self, *args, **opts):
        labels = GradePredictionLabel.objects.all()
        preds = GradePrediction.objects.all()
        scope = "platform"
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(f"No school '{opts['school']}'.") from exc
            labels = labels.filter(school_id=school.id)
            preds = preds.filter(school_id=school.id)
            scope = f"school={school.slug}"
        else:
            # tenant-isolation-allow: platform-wide audit
            pass
        if opts.get("academic_year"):
            labels = labels.filter(academic_year_id=opts["academic_year"])
            preds = preds.filter(academic_year_id=opts["academic_year"])
        if opts.get("term"):
            labels = labels.filter(term_id=opts["term"])
            preds = preds.filter(term_id=opts["term"])

        pred_lookup: dict[tuple, float] = {}
        for row in preds.values(
            "student_id", "subject_id", "academic_year_id",
            "term_id", "predicted_grade",
        ):
            key = (
                row["student_id"], row["subject_id"],
                row["academic_year_id"], row["term_id"],
            )
            pred_lookup[key] = float(row["predicted_grade"])

        per_bin_count = defaultdict(int)
        per_bin_pred_sum = defaultdict(float)
        per_bin_actual_sum = defaultdict(float)
        per_bin_abs_err = defaultdict(float)
        total_abs_err = 0.0
        total_sq_err = 0.0
        joined = 0
        for label in labels.values(
            "student_id", "subject_id", "academic_year_id",
            "term_id", "actual_grade",
        ):
            key = (
                label["student_id"], label["subject_id"],
                label["academic_year_id"], label["term_id"],
            )
            pred = pred_lookup.get(key)
            if pred is None:
                continue
            actual = float(label["actual_grade"])
            b = _bin(pred)
            err = pred - actual
            per_bin_count[b] += 1
            per_bin_pred_sum[b] += pred
            per_bin_actual_sum[b] += actual
            per_bin_abs_err[b] += abs(err)
            total_abs_err += abs(err)
            total_sq_err += err * err
            joined += 1
        if not joined:
            raise CommandError(
                f"No prediction/label join for scope={scope}."
            )
        overall_mae = total_abs_err / joined
        overall_rmse = math.sqrt(total_sq_err / joined)
        bins_payload = []
        min_n = opts["min_samples_per_bin"]
        for b in range(_BIN_COUNT):
            n = per_bin_count[b]
            if n == 0:
                continue
            avg_pred = per_bin_pred_sum[b] / n
            avg_actual = per_bin_actual_sum[b] / n
            bin_mae = per_bin_abs_err[b] / n
            bins_payload.append({
                "bin": b, "lower": b * _BIN_WIDTH, "upper": (b + 1) * _BIN_WIDTH,
                "n": n, "avg_pred": avg_pred, "avg_actual": avg_actual,
                "bin_mae": bin_mae, "bias": avg_pred - avg_actual,
                "counted": n >= min_n,
            })
        report = {
            "scope": scope, "joined": joined,
            "overall_mae": overall_mae, "overall_rmse": overall_rmse,
            "bins": bins_payload,
        }
        self.stdout.write(
            f"Overall MAE={overall_mae:.3f} RMSE={overall_rmse:.3f} n={joined}"
        )
        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))
        if (
            opts.get("max_overall_mae") is not None
            and overall_mae > opts["max_overall_mae"]
        ):
            raise CommandError(
                f"Calibration gate: MAE={overall_mae:.3f} > "
                f"max={opts['max_overall_mae']}"
            )
