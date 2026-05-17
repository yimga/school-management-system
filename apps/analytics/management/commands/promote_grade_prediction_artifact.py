"""Promote a grade-prediction candidate to production. Atomic registry flip."""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User

logger = logging.getLogger(
    "apps.analytics.commands.promote_grade_prediction_artifact"
)


class Command(BaseCommand):
    help = "Promote a candidate grade-prediction artifact to production."

    def add_arguments(self, parser):
        parser.add_argument("model_version")
        parser.add_argument("--promoted-by-username", required=True)
        parser.add_argument("--max-mae", type=float, default=None)
        parser.add_argument("--max-rmse", type=float, default=None)
        parser.add_argument("--min-r2", type=float, default=None)
        parser.add_argument("--allow-rejected", action="store_true")

    def handle(self, *args, **opts):
        from apps.analytics.models import GradePredictionModelArtifact

        try:
            artifact = GradePredictionModelArtifact.objects.get(
                model_version=opts["model_version"]
            )
        except GradePredictionModelArtifact.DoesNotExist as exc:
            raise CommandError(
                f"No grade-prediction artifact '{opts['model_version']}'."
            ) from exc
        try:
            operator = User.objects.get(username=opts["promoted_by_username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No user '{opts['promoted_by_username']}'."
            ) from exc
        if (
            artifact.status == GradePredictionModelArtifact.Status.REJECTED
            and not opts.get("allow_rejected")
        ):
            raise CommandError(
                f"{artifact.model_version} is REJECTED. "
                "Pass --allow-rejected to override."
            )

        failures = []
        if (
            opts.get("max_mae") is not None
            and artifact.metric_mae is not None
            and artifact.metric_mae > opts["max_mae"]
        ):
            failures.append(
                f"mae={artifact.metric_mae:.3f} > {opts['max_mae']}"
            )
        if (
            opts.get("max_rmse") is not None
            and artifact.metric_rmse is not None
            and artifact.metric_rmse > opts["max_rmse"]
        ):
            failures.append(
                f"rmse={artifact.metric_rmse:.3f} > {opts['max_rmse']}"
            )
        if (
            opts.get("min_r2") is not None
            and artifact.metric_r2 is not None
            and artifact.metric_r2 < opts["min_r2"]
        ):
            failures.append(
                f"r2={artifact.metric_r2:.3f} < {opts['min_r2']}"
            )
        if failures:
            raise CommandError(
                "Promotion gates failed: " + "; ".join(failures)
            )

        previous = artifact.promote(by_user=operator)
        msg = f"Promoted grade-prediction {artifact.model_version}"
        if previous is not None:
            msg += f"; archived previous {previous.model_version}"
        self.stdout.write(self.style.SUCCESS(msg + "."))
