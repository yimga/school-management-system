"""Promote a candidate at-risk artifact to production.

Atomically flips one row to `production` and archives whichever row was
previously production. Loader picks up the new path on the next inference
call (cache is keyed by path, so no worker restart needed).

Optional gates the operator can opt into:
    --min-roc-auc / --min-average-precision / --max-ece
The promote refuses unless all stored metrics meet the supplied floors.
Skips the check when a metric is null (e.g. ECE not yet computed).
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User

logger = logging.getLogger("apps.analytics.commands.promote_at_risk_artifact")


class Command(BaseCommand):
    help = "Promote a candidate at-risk artifact to production."

    def add_arguments(self, parser):
        parser.add_argument("model_version")
        parser.add_argument(
            "--promoted-by-username",
            required=True,
            help="Username of the operator authorizing the promotion.",
        )
        parser.add_argument(
            "--min-roc-auc", type=float, default=None,
        )
        parser.add_argument(
            "--min-average-precision", type=float, default=None,
        )
        parser.add_argument(
            "--max-ece", type=float, default=None,
        )
        parser.add_argument(
            "--allow-rejected",
            action="store_true",
            help="By default, REJECTED rows cannot be promoted. Pass this to override.",
        )

    def handle(self, *args, **opts):
        from apps.analytics.models import AtRiskModelArtifact

        try:
            artifact = AtRiskModelArtifact.objects.get(
                model_version=opts["model_version"]
            )
        except AtRiskModelArtifact.DoesNotExist as exc:
            raise CommandError(
                f"No registered artifact with model_version='{opts['model_version']}'."
            ) from exc

        try:
            operator = User.objects.get(
                username=opts["promoted_by_username"]
            )
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No user '{opts['promoted_by_username']}'."
            ) from exc

        if (
            artifact.status == AtRiskModelArtifact.Status.REJECTED
            and not opts.get("allow_rejected")
        ):
            raise CommandError(
                f"Artifact {artifact.model_version} is REJECTED. "
                "Pass --allow-rejected to override (audit-visible)."
            )

        failures = []
        if (
            opts.get("min_roc_auc") is not None
            and artifact.metric_roc_auc is not None
            and artifact.metric_roc_auc < opts["min_roc_auc"]
        ):
            failures.append(
                f"roc_auc={artifact.metric_roc_auc:.3f} < {opts['min_roc_auc']}"
            )
        if (
            opts.get("min_average_precision") is not None
            and artifact.metric_average_precision is not None
            and artifact.metric_average_precision < opts["min_average_precision"]
        ):
            failures.append(
                f"avg_precision={artifact.metric_average_precision:.3f} "
                f"< {opts['min_average_precision']}"
            )
        if (
            opts.get("max_ece") is not None
            and artifact.metric_ece is not None
            and artifact.metric_ece > opts["max_ece"]
        ):
            failures.append(
                f"ece={artifact.metric_ece:.3f} > {opts['max_ece']}"
            )
        if failures:
            raise CommandError(
                "Promotion gates failed: " + "; ".join(failures)
            )

        previous = artifact.promote(by_user=operator)
        if previous is None:
            self.stdout.write(self.style.SUCCESS(
                f"Promoted {artifact.model_version} (no prior production row)."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Promoted {artifact.model_version}; "
                f"archived previous production {previous.model_version}."
            ))
