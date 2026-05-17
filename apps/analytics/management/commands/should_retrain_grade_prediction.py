"""Decide whether the grade-prediction model is due for a retrain.

Same shape as `should_retrain_at_risk`. Counts GradePredictionLabel
rows since the artifact's `trained_at`; checks artifact age. Exit
codes: 0 not due, 10 label threshold, 11 age.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.analytics.models import GradePredictionLabel
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.should_retrain_grade_prediction")

_EXIT_NOT_DUE = 0
_EXIT_LABEL_THRESHOLD = 10
_EXIT_AGE = 11
_DEFAULT_LABEL_THRESHOLD = 100
_DEFAULT_MAX_AGE_DAYS = 180


def _bundle_trained_at(artifact_path: Path) -> datetime:
    try:
        import joblib
    except ImportError:
        return _from_mtime(artifact_path)
    try:
        bundle = joblib.load(artifact_path)
    except (FileNotFoundError, OSError, EOFError, ValueError):
        return _from_mtime(artifact_path)
    if not isinstance(bundle, dict):
        return _from_mtime(artifact_path)
    raw = bundle.get("trained_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return _from_mtime(artifact_path)


def _from_mtime(artifact_path: Path) -> datetime:
    if not artifact_path.exists():
        return datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
    return datetime.fromtimestamp(
        os.path.getmtime(artifact_path), tz=dt_timezone.utc
    )


class Command(BaseCommand):
    help = "Exit non-zero when the grade-prediction model should be retrained."

    def add_arguments(self, parser):
        parser.add_argument("--artifact", required=True)
        parser.add_argument(
            "--threshold", type=int, default=_DEFAULT_LABEL_THRESHOLD,
        )
        parser.add_argument(
            "--max-age-days", type=int, default=_DEFAULT_MAX_AGE_DAYS,
        )
        parser.add_argument("--school", default=None)
        parser.add_argument("--threshold-only", action="store_true")
        parser.add_argument("--max-age-only", action="store_true")

    def handle(self, *args, **opts):
        artifact_path = Path(opts["artifact"])
        trained_at = _bundle_trained_at(artifact_path)
        labels = GradePredictionLabel.objects.filter(labeled_at__gt=trained_at)
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(f"No school '{opts['school']}'.") from exc
            labels = labels.filter(school_id=school.id)
        else:
            # tenant-isolation-allow: operator cron — platform-wide signal default.
            pass
        new_count = labels.count()
        age_days = (timezone.now() - trained_at).days
        label_due = (
            new_count >= opts["threshold"] and not opts.get("max_age_only")
        )
        age_due = (
            age_days >= opts["max_age_days"] and not opts.get("threshold_only")
        )

        decision = "not_due"
        exit_code = _EXIT_NOT_DUE
        if label_due:
            decision = "label_threshold"
            exit_code = _EXIT_LABEL_THRESHOLD
        elif age_due:
            decision = "max_age"
            exit_code = _EXIT_AGE

        self.stdout.write(
            f"decision={decision} new_labels={new_count}/{opts['threshold']} "
            f"age_days={age_days}/{opts['max_age_days']}"
        )
        if exit_code != _EXIT_NOT_DUE:
            raise SystemExit(exit_code)
