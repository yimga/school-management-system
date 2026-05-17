"""Measure calibration of production at-risk model.

A model is *calibrated* when predicted probabilities match observed
frequencies — e.g. of students given score 70-80, ~75% should actually
turn out at-risk.

We join `AtRiskOutcomeLabel` (ground truth) to the most recent
`RiskFactor.score` for that (student, academic_year) and bin into 10
equal-width buckets. For each bucket we compute:

  - n           — number of labeled rows in the bucket
  - avg_pred    — average predicted score / 100 (treated as probability)
  - observed    — fraction of bucket labelled AT_RISK / RECOVERED

Expected Calibration Error (ECE):
  weighted-mean |avg_pred - observed|, weighted by bucket size.

ECE < 0.10 is usable in production; >0.15 typically requires recalibration
(isotonic / Platt) before re-deploy.

The `RECOVERED` label counts as a positive: the prediction was correctly
flagging the student before intervention worked.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.analytics.models import AtRiskOutcomeLabel, RiskFactor
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.check_at_risk_calibration")

_BIN_COUNT = 10
_POSITIVE_LABELS = {
    AtRiskOutcomeLabel.Label.AT_RISK,
    AtRiskOutcomeLabel.Label.RECOVERED,
}


def _bin(prob: float) -> int:
    if prob >= 1.0:
        return _BIN_COUNT - 1
    if prob <= 0.0:
        return 0
    return min(int(prob * _BIN_COUNT), _BIN_COUNT - 1)


class Command(BaseCommand):
    help = "Measure ECE of production RiskFactor scores against AtRiskOutcomeLabel."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            default=None,
            help="School slug to scope to. Omit for platform-wide.",
        )
        parser.add_argument(
            "--academic-year",
            default=None,
            help="Academic year ID. Omit to use all labelled years.",
        )
        parser.add_argument(
            "--min-samples-per-bin",
            type=int,
            default=5,
            help="Bins with fewer rows than this are excluded from ECE (too noisy).",
        )
        parser.add_argument(
            "--max-ece",
            type=float,
            default=None,
            help="Optional gate: exit non-zero if ECE exceeds this floor.",
        )
        parser.add_argument(
            "--json",
            default=None,
            help="Optional JSON report output path.",
        )

    def handle(self, *args, **opts):
        labels_qs = AtRiskOutcomeLabel.objects.all()
        scope = "platform"
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(f"No school with slug '{opts['school']}'") from exc
            labels_qs = labels_qs.filter(school_id=school.id)
            scope = f"school={school.slug}"
        else:
            # tenant-isolation-allow: operator-invoked platform-wide calibration audit.
            pass
        if opts.get("academic_year"):
            labels_qs = labels_qs.filter(academic_year_id=opts["academic_year"])

        n_labels = labels_qs.count()
        if not n_labels:
            raise CommandError(f"No AtRiskOutcomeLabel rows for scope={scope}.")

        # tenant-isolation-allow: latest_per_pair is a small set scoped via
        # the FK join below; the filter happens in `score_lookup` build.
        pairs = labels_qs.values_list("student_id", "academic_year_id")
        student_ids = {p[0] for p in pairs}

        # For each student, keep the most-recent RiskFactor.score. RiskFactor
        # doesn't carry academic_year directly; the most-recent score is the
        # honest signal of what the model said about this student.
        # tenant-isolation-allow: student_id__in is a subset of labels_qs (already school-scoped).
        rf_rows = RiskFactor.objects.filter(
            student_id__in=student_ids,
        ).values("student_id", "computed_at", "score")
        latest_rf: dict[int, tuple] = {}
        for row in rf_rows:
            existing = latest_rf.get(row["student_id"])
            if existing is None or row["computed_at"] > existing[0]:
                latest_rf[row["student_id"]] = (
                    row["computed_at"],
                    float(row["score"]),
                )
        score_lookup: dict[int, float] = {
            sid: score for sid, (_ts, score) in latest_rf.items()
        }

        # Build (probability, is_positive) pairs.
        per_bin_sum = defaultdict(float)
        per_bin_pos = defaultdict(int)
        per_bin_n = defaultdict(int)
        joined_count = 0
        missing_score = 0
        for label_row in labels_qs.values("student_id", "label"):
            student_id = label_row["student_id"]
            score = score_lookup.get(student_id)
            if score is None:
                missing_score += 1
                continue
            prob = max(0.0, min(1.0, score / 100.0))
            b = _bin(prob)
            per_bin_sum[b] += prob
            per_bin_n[b] += 1
            if label_row["label"] in _POSITIVE_LABELS:
                per_bin_pos[b] += 1
            joined_count += 1

        bins_payload = []
        ece_numerator = 0.0
        ece_denominator = 0
        min_n = opts["min_samples_per_bin"]
        for b in range(_BIN_COUNT):
            n = per_bin_n[b]
            if n == 0:
                continue
            avg_pred = per_bin_sum[b] / n
            observed = per_bin_pos[b] / n
            bins_payload.append({
                "bin": b,
                "lower": b / _BIN_COUNT,
                "upper": (b + 1) / _BIN_COUNT,
                "n": n,
                "avg_pred": avg_pred,
                "observed_positive_rate": observed,
                "gap": abs(avg_pred - observed),
                "counted_in_ece": n >= min_n,
            })
            if n >= min_n:
                ece_numerator += n * abs(avg_pred - observed)
                ece_denominator += n
        ece = ece_numerator / ece_denominator if ece_denominator else None

        report = {
            "scope": scope,
            "labels_total": n_labels,
            "joined_to_predictions": joined_count,
            "missing_predictions": missing_score,
            "min_samples_per_bin": min_n,
            "ece": ece,
            "bins": bins_payload,
        }
        if ece is None:
            self.stdout.write(
                "ECE=n/a — every bin below --min-samples-per-bin "
                f"({min_n}); collect more labels."
            )
        else:
            self.stdout.write(
                f"ECE={ece:.4f} over {ece_denominator} usable rows; "
                f"joined {joined_count}/{n_labels} labels to predictions."
            )
        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))
            self.stdout.write(self.style.SUCCESS(f"Wrote {opts['json']}"))

        if (
            opts.get("max_ece") is not None
            and ece is not None
            and ece > opts["max_ece"]
        ):
            raise CommandError(
                f"Calibration gate failed: ECE={ece:.3f} > max={opts['max_ece']:.3f}"
            )
