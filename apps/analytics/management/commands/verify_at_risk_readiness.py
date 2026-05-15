"""Wave O1 — at-risk ML artifact readiness preflight CLI."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Preflight: verify the at-risk predictor will fire the ML "
        "inference path (artifact resolves, loads, has valid bundle shape) "
        "or report heuristic-mode cleanly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet", action="store_true",
            help="Suppress per-row output; rely on exit code (0=ready, 1=not).",
        )

    def handle(self, *args, **opts):
        from apps.analytics.at_risk_readiness import assess_at_risk_readiness

        quiet = bool(opts.get("quiet"))
        report = assess_at_risk_readiness()

        if not quiet:
            self._render(report)

        if not report.ready:
            raise SystemExit(1)

    def _render(self, report) -> None:  # noqa: ANN001
        self.stdout.write("=== At-risk ML artifact readiness preflight ===")
        self.stdout.write(f"Mode:                   {report.mode}")
        self.stdout.write(
            f"Resolved path:          {report.resolved_path or '(none — heuristic-only)'}"
        )
        if report.resolved_path:
            self.stdout.write(
                f"Artifact exists:        {'YES' if report.artifact_exists else 'NO'}"
            )
            if report.artifact_exists:
                self.stdout.write(
                    f"Artifact loadable:      {'YES' if report.artifact_loadable else 'NO'}"
                )
                self.stdout.write(
                    f"Bundle shape valid:     {'YES' if report.bundle_shape_valid else 'NO'}"
                )
                if report.bundle_model_version:
                    self.stdout.write(
                        f"Bundle model_version:   {report.bundle_model_version}"
                    )
        if report.error_detail:
            tag = "..  " if report.ready else "!!  "
            self.stdout.write(f"{tag}detail: {report.error_detail}")

        self.stdout.write("")
        if report.mode == "heuristic":
            self.stdout.write(self.style.SUCCESS(
                "READY (heuristic mode) — predictor uses rule-based scoring.\n"
                "To enable ML: `manage.py train_at_risk_baseline --clear-cache` "
                "or set AT_RISK_MODEL_PATH to a joblib bundle."
            ))
        elif report.mode == "ml-artifact":
            self.stdout.write(self.style.SUCCESS(
                "READY (ml-artifact mode) — predictor will use the loaded model."
            ))
        else:  # misconfigured
            self.stdout.write(self.style.WARNING(
                "NOT READY — artifact path is set but unusable. "
                "Predictor would silently fall back to heuristic. "
                "Resolve the detail above or unset AT_RISK_MODEL_PATH "
                "to accept heuristic-only mode."
            ))
