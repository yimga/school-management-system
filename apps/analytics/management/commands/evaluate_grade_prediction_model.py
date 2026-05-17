"""Evaluate the grade-prediction model against actual end-of-term labels.

Computes regression metrics (MAE, RMSE, R²) by joining
`GradePrediction` rows to `GradePredictionLabel` rows on the
(student, subject, academic_year, term) key. Optionally enforces a
deploy gate (`--max-mae`).

Tenant-scoped via `--school`; platform-wide when omitted.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import GradePrediction, GradePredictionLabel
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.evaluate_grade_prediction_model")


class Command(BaseCommand):
    help = "Compute MAE / RMSE / R² of grade predictions vs actual labels."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", default=None,
            help="School slug to scope to; omit for platform-wide.",
        )
        parser.add_argument("--academic-year", default=None)
        parser.add_argument("--term", default=None)
        parser.add_argument(
            "--max-mae", type=float, default=None,
            help="Optional gate: exit non-zero if MAE exceeds this floor.",
        )
        parser.add_argument(
            "--json", default=None, help="Optional JSON output path."
        )

    def handle(self, *args, **opts):
        labels_qs = GradePredictionLabel.objects.all()
        preds_qs = GradePrediction.objects.all()
        scope = "platform"
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(
                    f"No school '{opts['school']}'."
                ) from exc
            labels_qs = labels_qs.filter(school_id=school.id)
            preds_qs = preds_qs.filter(school_id=school.id)
            scope = f"school={school.slug}"
        else:
            # tenant-isolation-allow: operator-invoked platform-wide audit.
            pass
        if opts.get("academic_year"):
            labels_qs = labels_qs.filter(academic_year_id=opts["academic_year"])
            preds_qs = preds_qs.filter(academic_year_id=opts["academic_year"])
        if opts.get("term"):
            labels_qs = labels_qs.filter(term_id=opts["term"])
            preds_qs = preds_qs.filter(term_id=opts["term"])

        # Build lookup: (student, subject, year, term) → predicted_grade
        pred_lookup = {}
        for row in preds_qs.values(
            "student_id", "subject_id", "academic_year_id",
            "term_id", "predicted_grade",
        ):
            key = (
                row["student_id"], row["subject_id"],
                row["academic_year_id"], row["term_id"],
            )
            pred_lookup[key] = float(row["predicted_grade"])

        errors = []
        actuals = []
        joined = 0
        missing = 0
        for label in labels_qs.values(
            "student_id", "subject_id", "academic_year_id",
            "term_id", "actual_grade",
        ):
            key = (
                label["student_id"], label["subject_id"],
                label["academic_year_id"], label["term_id"],
            )
            pred = pred_lookup.get(key)
            if pred is None:
                missing += 1
                continue
            actual = float(label["actual_grade"])
            errors.append(pred - actual)
            actuals.append(actual)
            joined += 1

        if not errors:
            raise CommandError(
                f"No prediction/label join for scope={scope}; need both rows."
            )

        n = len(errors)
        mae = sum(abs(e) for e in errors) / n
        rmse = math.sqrt(sum(e ** 2 for e in errors) / n)
        # R² = 1 - SS_res / SS_tot; SS_tot uses actuals.
        actual_mean = sum(actuals) / n
        ss_res = sum(e ** 2 for e in errors)
        ss_tot = sum((a - actual_mean) ** 2 for a in actuals) or 1.0
        r2 = 1.0 - ss_res / ss_tot

        report = {
            "scope": scope,
            "joined": joined,
            "missing_predictions": missing,
            "metrics": {"mae": mae, "rmse": rmse, "r2": r2},
        }
        self.stdout.write(
            f"MAE={mae:.3f}  RMSE={rmse:.3f}  R²={r2:.3f}  (n={n})"
        )
        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))
            self.stdout.write(self.style.SUCCESS(f"Wrote {opts['json']}"))

        if opts.get("max_mae") is not None and mae > opts["max_mae"]:
            raise CommandError(
                f"Eval gate failed: MAE={mae:.3f} > max={opts['max_mae']}"
            )
