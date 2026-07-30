"""Register a trained joblib bundle in the at-risk model registry.

A registered row enters as `candidate` — the operator must explicitly
`promote_at_risk_artifact` to make it live. This two-step is deliberate:
auto-promote on register is how teams end up serving a regressed model
because the gates were lax.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.accounts.models import User

logger = logging.getLogger("apps.analytics.commands.register_at_risk_artifact")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Command(BaseCommand):
    help = "Register a trained at-risk joblib bundle as a candidate artifact."

    def add_arguments(self, parser):
        parser.add_argument("artifact")
        parser.add_argument(
            "--model-version",
            required=True,
            help="Stable identifier — must be unique across all registered rows.",
        )
        parser.add_argument(
            "--registered-by-username",
            required=True,
            help="Username of the operator running the registration.",
        )
        parser.add_argument(
            "--training-csv",
            default=None,
            help="Optional path to the training CSV — hash + row count get captured.",
        )
        parser.add_argument(
            "--eval-json",
            default=None,
            help="Path to an `evaluate_at_risk_model --json` report; metrics copy in.",
        )
        parser.add_argument(
            "--notes",
            default="",
            help="Free-form notes (training run ID, intent, etc.).",
        )

    def handle(self, *args, **opts):
        from apps.analytics.models import AtRiskModelArtifact

        artifact_path = Path(opts["artifact"])
        if not artifact_path.exists():
            raise CommandError(f"Artifact not found: {artifact_path}")

        try:
            operator = User.objects.get(username=opts["registered_by_username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No user with username '{opts['registered_by_username']}'."
            ) from exc

        if AtRiskModelArtifact.objects.filter(
            model_version=opts["model_version"]
        ).exists():
            raise CommandError(
                f"Model version '{opts['model_version']}' already registered."
            )

        # Pull trained_at, feature_order, training_row_count from the bundle.
        trained_at = timezone.now()
        feature_order: list = []
        training_row_count = 0
        try:
            import joblib  # type: ignore
        except ImportError:
            self.stdout.write(
                "joblib not installed — bundle metadata not extracted; "
                "registration will record artifact path only."
            )
        else:
            try:
                bundle = joblib.load(artifact_path)
                if isinstance(bundle, dict):
                    ts_raw = bundle.get("trained_at")
                    if isinstance(ts_raw, str):
                        try:
                            from datetime import datetime
                            trained_at = datetime.fromisoformat(
                                ts_raw.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass
                    feature_order = list(bundle.get("feature_order") or [])
                    training_row_count = int(
                        bundle.get("training_row_count") or 0
                    )
            except Exception as exc:  # noqa: BLE001
                # Best-effort metadata: a corrupt / non-bundle artifact (or any
                # unpickle failure) must not sink registration — fall back to the
                # path-only record, same as the joblib-missing branch.
                self.stdout.write(
                    f"artifact bundle metadata not extractable "
                    f"({exc.__class__.__name__}); registration will record "
                    "artifact path + supplied metadata only."
                )

        training_dataset_hash = ""
        if opts.get("training_csv"):
            csv_path = Path(opts["training_csv"])
            if not csv_path.exists():
                raise CommandError(f"--training-csv not found: {csv_path}")
            training_dataset_hash = _sha256_of(csv_path)
            if not training_row_count:
                with open(csv_path, encoding="utf-8") as f:
                    training_row_count = sum(1 for _ in f) - 1  # header

        roc_auc = avg_prec = ece = None
        if opts.get("eval_json"):
            eval_payload = json.loads(Path(opts["eval_json"]).read_text())
            metrics = eval_payload.get("metrics") or {}
            roc_auc = metrics.get("roc_auc")
            avg_prec = metrics.get("average_precision")
            ece = eval_payload.get("ece") or metrics.get("ece")

        row = AtRiskModelArtifact.objects.create(
            model_version=opts["model_version"],
            artifact_path=str(artifact_path),
            trained_at=trained_at,
            training_dataset_hash=training_dataset_hash,
            training_row_count=training_row_count,
            feature_order=feature_order,
            metric_roc_auc=roc_auc,
            metric_average_precision=avg_prec,
            metric_ece=ece,
            status=AtRiskModelArtifact.Status.CANDIDATE,
            registered_by=operator,
            notes=opts["notes"],
        )
        self.stdout.write(self.style.SUCCESS(
            f"Registered {row.model_version} [candidate] id={row.pk}"
        ))
