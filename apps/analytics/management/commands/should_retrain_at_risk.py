"""Decide whether the at-risk model is due for a retrain.

Returns a structured signal an operator (or CI cron) can act on. Used in
the production retrain loop where the trigger is "enough new labelled
outcomes have accumulated since the deployed artifact was trained."

Exit codes:
    0   not due (or unable to decide)
    10  retrain due — new label volume crossed --threshold
    11  retrain due — model age crossed --max-age-days

The non-zero codes are distinct so an orchestrator can branch.

Decision inputs (whichever fires first):
    * `--threshold N` (default 100): number of `AtRiskOutcomeLabel` rows
      created since the artifact's `trained_at` (read from joblib bundle
      `model_version`/`trained_at` keys; falls back to file mtime).
    * `--max-age-days D` (default 180): hard cap so models can't go stale
      even when labels are sparse.

Both gates are independent — supplying `--threshold-only` or
`--max-age-only` lets ops disable one signal during commissioning.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.analytics.models import AtRiskOutcomeLabel
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.should_retrain_at_risk")

_EXIT_NOT_DUE = 0
_EXIT_LABEL_THRESHOLD = 10
_EXIT_AGE = 11

# Defaults stated as module constants so the magic-numbers scanner stays clean
# and operators can override per environment in cron wrappers.
_DEFAULT_LABEL_THRESHOLD = 100
_DEFAULT_MAX_AGE_DAYS = 180


def _bundle_trained_at(artifact_path: Path) -> datetime:
    """Best-effort read of when this artifact was trained.

    Bundles emitted by `train_at_risk.py` may include either a
    `trained_at` ISO-8601 string or embed it into `model_version`.
    When unreadable we fall back to file mtime so the age gate still
    fires sensibly even on legacy bundles.
    """
    try:
        import joblib  # type: ignore
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
        # Treat missing artifact as ancient so age-gate triggers a retrain.
        return datetime(1970, 1, 1, tzinfo=dt_timezone.utc)
    return datetime.fromtimestamp(
        os.path.getmtime(artifact_path), tz=dt_timezone.utc
    )


class Command(BaseCommand):
    help = "Exit non-zero when the at-risk model should be retrained."

    def add_arguments(self, parser):
        parser.add_argument("--artifact", required=True)
        parser.add_argument(
            "--threshold", type=int, default=_DEFAULT_LABEL_THRESHOLD,
        )
        parser.add_argument(
            "--max-age-days", type=int, default=_DEFAULT_MAX_AGE_DAYS,
        )
        parser.add_argument(
            "--school", default=None, help="Scope the label count to one tenant."
        )
        parser.add_argument(
            "--threshold-only", action="store_true",
            help="Ignore the age-gate; decide only on new label volume.",
        )
        parser.add_argument(
            "--max-age-only", action="store_true",
            help="Ignore the label-volume gate; decide only on age.",
        )
        parser.add_argument(
            "--json", default=None, help="Optional JSON output path."
        )

    def handle(self, *args, **opts):
        artifact_path = Path(opts["artifact"])
        trained_at = _bundle_trained_at(artifact_path)

        labels_qs = AtRiskOutcomeLabel.objects.filter(labeled_at__gt=trained_at)
        scope = "platform"
        if opts.get("school"):
            try:
                school = School.objects.get(slug=opts["school"])
            except School.DoesNotExist as exc:
                raise CommandError(f"No school with slug '{opts['school']}'") from exc
            labels_qs = labels_qs.filter(school_id=school.id)
            scope = f"school={school.slug}"
        else:
            # tenant-isolation-allow: operator cron tool; platform-wide signal by default.
            pass
        new_label_count = labels_qs.count()

        age_days = (timezone.now() - trained_at).days
        threshold = opts["threshold"]
        max_age = opts["max_age_days"]

        label_due = (
            new_label_count >= threshold and not opts.get("max_age_only")
        )
        age_due = age_days >= max_age and not opts.get("threshold_only")

        decision = "not_due"
        exit_code = _EXIT_NOT_DUE
        if label_due:
            decision = "label_threshold"
            exit_code = _EXIT_LABEL_THRESHOLD
        elif age_due:
            decision = "max_age"
            exit_code = _EXIT_AGE

        report = {
            "artifact": str(artifact_path),
            "trained_at": trained_at.isoformat(),
            "scope": scope,
            "new_labels_since_training": new_label_count,
            "threshold": threshold,
            "age_days": age_days,
            "max_age_days": max_age,
            "decision": decision,
            "exit_code": exit_code,
        }
        self.stdout.write(
            f"decision={decision} new_labels={new_label_count}/{threshold} "
            f"age_days={age_days}/{max_age}"
        )
        if opts.get("json"):
            Path(opts["json"]).parent.mkdir(parents=True, exist_ok=True)
            Path(opts["json"]).write_text(json.dumps(report, indent=2))

        if exit_code != _EXIT_NOT_DUE:
            # CommandError exits 1 which collapses two signals; use SystemExit
            # to preserve the distinct exit codes.
            raise SystemExit(exit_code)
