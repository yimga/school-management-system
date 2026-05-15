"""Wave O4 (2026-05-15): export labeled at-risk training data to CSV.

Joins ``AtRiskOutcomeLabel`` rows with feature extraction (via
``apps.analytics.ml.at_risk_features.extract_features``) to emit a CSV
whose schema matches ``train_at_risk.py --csv``:

    attendance_rate,absence_count,late_count,avg_evaluation_score,
    evaluation_count,eval_score_trend,open_invoice_count,
    open_balance_amount,days_since_last_login,label

``label`` is the binary 0/1 target:

* ``at_risk``  → 1
* ``recovered`` → 1 (the student *was* at risk; the intervention worked,
                     but the historical signal we want to learn is the
                     at-risk state)
* ``not_at_risk`` → 0
* ``unknown`` → row skipped (insufficient training signal)

Usage:
    python manage.py export_at_risk_training_data
    python manage.py export_at_risk_training_data --out var/at_risk_train.csv
    python manage.py export_at_risk_training_data --school <slug>
    python manage.py export_at_risk_training_data --year <academic_year_id>

Round-trip:
    1. Principals label outcomes via /portal/at-risk/labeling/.
    2. `python manage.py export_at_risk_training_data --out X.csv`
    3. `python manage.py train_at_risk_baseline --csv X.csv --clear-cache`
    4. Next predict_at_risk() call uses the freshly-trained artifact.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)

# Maps the four label TextChoices to either {0, 1} or None (skip).
_LABEL_TO_TARGET: dict[str, int | None] = {
    "at_risk": 1,
    "recovered": 1,
    "not_at_risk": 0,
    "unknown": None,
}


class Command(BaseCommand):
    help = "Export labeled at-risk training data to a CSV consumable by train_at_risk.py --csv."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out", type=str, default="var/at_risk_train.csv",
            help="Output CSV path (default: var/at_risk_train.csv).",
        )
        parser.add_argument(
            "--school", type=str, default="",
            help="Restrict export to one school by slug.",
        )
        parser.add_argument(
            "--year", type=int, default=0,
            help="Restrict to one AcademicYear id (0 = all).",
        )

    def handle(self, *args, **opts):
        from apps.analytics.ml.at_risk_features import extract_features
        from apps.analytics.ml.synthetic_at_risk_dataset import FEATURE_ORDER
        from apps.analytics.models import AtRiskOutcomeLabel

        out_path = Path(opts["out"])
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # tenant-isolation-allow: export tool sweeps all tenants with labels by design
        qs = AtRiskOutcomeLabel.objects.select_related(
            "student", "school", "academic_year"
        )
        slug = (opts.get("school") or "").strip()
        if slug:
            qs = qs.filter(school__slug=slug)
        year_id = int(opts.get("year") or 0)
        if year_id:
            qs = qs.filter(academic_year_id=year_id)

        written = 0
        skipped_unknown = 0
        skipped_feature_extract = 0

        fieldnames = list(FEATURE_ORDER) + ["label"]
        with out_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()

            for outcome in qs.iterator():
                target = _LABEL_TO_TARGET.get(outcome.label)
                if target is None:
                    skipped_unknown += 1
                    continue
                try:
                    features = extract_features(outcome.student)
                except Exception as exc:  # noqa: BLE001 — keep one bad row from killing export
                    logger.warning(
                        "feature extraction failed for student=%s: %s",
                        outcome.student_id, exc,
                    )
                    skipped_feature_extract += 1
                    continue
                row = {name: getattr(features, name, 0) for name in FEATURE_ORDER}
                row["label"] = target
                writer.writerow(row)
                written += 1

        self.stdout.write(self.style.SUCCESS(
            f"wrote {written} row(s) to {out_path}"
        ))
        if skipped_unknown:
            self.stdout.write(
                f"  skipped {skipped_unknown} 'unknown' label(s) (no training signal)"
            )
        if skipped_feature_extract:
            self.stdout.write(self.style.WARNING(
                f"  skipped {skipped_feature_extract} row(s) where feature extraction failed"
            ))
        if written == 0:
            raise CommandError(
                "no rows exported. Label at least a few students via "
                "/portal/at-risk/labeling/ first."
            )
