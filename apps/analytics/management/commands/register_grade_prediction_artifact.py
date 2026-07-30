"""Register a trained grade-prediction joblib as a candidate registry row.

Mirror of `register_at_risk_artifact` for the grade-prediction family.
Reads `trained_at`, `feature_order`, `training_row_count`,
`holdout_metrics` from the bundle when present.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User

logger = logging.getLogger(
    "apps.analytics.commands.register_grade_prediction_artifact"
)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Register a grade-prediction joblib as a candidate artifact."

    def add_arguments(self, parser):
        parser.add_argument("artifact")
        parser.add_argument("--model-version", required=True)
        parser.add_argument("--registered-by-username", required=True)
        parser.add_argument("--training-csv", default=None)
        parser.add_argument("--eval-json", default=None)
        parser.add_argument("--notes", default="")

    def handle(self, *args, **opts):
        from apps.analytics.models import GradePredictionModelArtifact

        artifact_path = Path(opts["artifact"])
        if not artifact_path.exists():
            raise CommandError(f"Artifact not found: {artifact_path}")

        try:
            operator = User.objects.get(username=opts["registered_by_username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No user '{opts['registered_by_username']}'."
            ) from exc

        if GradePredictionModelArtifact.objects.filter(
            model_version=opts["model_version"]
        ).exists():
            raise CommandError(
                f"Model version '{opts['model_version']}' already registered."
            )

        trained_at = timezone.now()
        feature_order: list = []
        training_row_count = 0
        holdout_metrics: dict = {}
        try:
            import joblib  # type: ignore
        except ImportError:
            self.stdout.write(
                "joblib not installed — bundle metadata not extracted."
            )
        else:
            try:
                bundle = joblib.load(artifact_path)
                if isinstance(bundle, dict):
                    ts_raw = bundle.get("trained_at")
                    if isinstance(ts_raw, str):
                        try:
                            trained_at = datetime.fromisoformat(
                                ts_raw.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass
                    feature_order = list(bundle.get("feature_order") or [])
                    training_row_count = int(bundle.get("training_row_count") or 0)
                    holdout_metrics = dict(bundle.get("holdout_metrics") or {})
            except Exception as exc:  # noqa: BLE001
                # Best-effort metadata: a corrupt / non-bundle artifact must not
                # sink registration — record the path + supplied metadata only.
                self.stdout.write(
                    f"artifact bundle metadata not extractable "
                    f"({exc.__class__.__name__})."
                )

        mae = holdout_metrics.get("mae")
        rmse = holdout_metrics.get("rmse")
        r2 = holdout_metrics.get("r2")
        if opts.get("eval_json"):
            payload = json.loads(Path(opts["eval_json"]).read_text())
            metrics = payload.get("metrics") or {}
            mae = metrics.get("mae", mae)
            rmse = metrics.get("rmse", rmse)
            r2 = metrics.get("r2", r2)

        training_dataset_hash = ""
        if opts.get("training_csv"):
            csv_path = Path(opts["training_csv"])
            if not csv_path.exists():
                raise CommandError(f"--training-csv not found: {csv_path}")
            training_dataset_hash = _sha256_of(csv_path)
            if not training_row_count:
                with open(csv_path, encoding="utf-8") as f:
                    training_row_count = sum(1 for _ in f) - 1

        row = GradePredictionModelArtifact.objects.create(
            model_version=opts["model_version"],
            artifact_path=str(artifact_path),
            trained_at=trained_at,
            training_dataset_hash=training_dataset_hash,
            training_row_count=training_row_count,
            feature_order=feature_order,
            metric_mae=mae,
            metric_rmse=rmse,
            metric_r2=r2,
            status=GradePredictionModelArtifact.Status.CANDIDATE,
            registered_by=operator,
            notes=opts["notes"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Registered grade-prediction artifact {row.model_version} [candidate]"
        ))
