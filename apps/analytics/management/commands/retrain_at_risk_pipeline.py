"""Orchestrate the at-risk retrain loop end-to-end.

Chains the existing single-step commands so a cron entry only has to call
one thing. Each step is opt-out via a flag so operators can dry-run any
portion.

Loop:

    1. `should_retrain_at_risk` — exit 0 means no work to do; otherwise
       continue.
    2. `export_at_risk_training_data` (per --school) → CSV in --work-dir.
    3. `train_at_risk.py` (subprocess to keep memory clean) → candidate
       joblib in --work-dir.
    4. `evaluate_at_risk_model` against --holdout-csv → JSON report.
    5. `register_at_risk_artifact` → AtRiskModelArtifact row (candidate).

Promotion is **never** automatic. The orchestrator stops at candidate.
The operator reviews Wave 2 shadow-comparison evidence (when available)
before running `promote_at_risk_artifact`.

Exit codes:
    0   pipeline ran to candidate-registered
    20  no retrain needed (should_retrain returned 0)
    21  pipeline aborted at a step (label export, train, eval) — see stderr
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

logger = logging.getLogger("apps.analytics.commands.retrain_at_risk_pipeline")

_EXIT_OK = 0
_EXIT_NOT_DUE = 20
_EXIT_PIPELINE_ABORTED = 21


class Command(BaseCommand):
    help = "Run the at-risk retrain loop end-to-end (label → train → eval → register)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--current-artifact",
            required=True,
            help="Path to the currently-deployed joblib bundle. Drives "
            "should_retrain_at_risk decision and trained_at fallback.",
        )
        parser.add_argument(
            "--school", required=True,
            help="School slug to export labels for.",
        )
        parser.add_argument(
            "--work-dir",
            required=True,
            help="Directory for intermediate CSV / candidate joblib / eval JSON.",
        )
        parser.add_argument(
            "--operator-username",
            required=True,
            help="User on whose behalf the candidate row is registered.",
        )
        parser.add_argument(
            "--threshold", type=int, default=100,
        )
        parser.add_argument(
            "--max-age-days", type=int, default=180,
        )
        parser.add_argument(
            "--holdout-csv", default=None,
            help="Optional reserved holdout CSV the trainer never saw.",
        )
        parser.add_argument(
            "--min-roc-auc", type=float, default=0.70,
        )
        parser.add_argument(
            "--min-average-precision", type=float, default=0.40,
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip the should_retrain_at_risk gate (force retrain).",
        )
        parser.add_argument(
            "--skip-train",
            action="store_true",
            help="Stop after label export + holdout-quality check; for dry runs.",
        )

    def handle(self, *args, **opts):
        work_dir = Path(opts["work_dir"])
        work_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: should we even bother?
        if not opts["force"]:
            try:
                call_command(
                    "should_retrain_at_risk",
                    "--artifact", opts["current_artifact"],
                    "--threshold", str(opts["threshold"]),
                    "--max-age-days", str(opts["max_age_days"]),
                    "--school", opts["school"],
                    stdout=self.stdout,
                )
            except SystemExit as exit_signal:
                # 10 (label threshold) or 11 (age) → continue to retrain.
                if exit_signal.code not in (10, 11):
                    sys.exit(_EXIT_NOT_DUE)
            else:
                # Exit code 0 → not due.
                self.stdout.write("No retrain needed; exiting.")
                sys.exit(_EXIT_NOT_DUE)

        stamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        training_csv = work_dir / f"training_{opts['school']}_{stamp}.csv"
        candidate_joblib = work_dir / f"candidate_{opts['school']}_{stamp}.joblib"
        eval_report = work_dir / f"eval_{opts['school']}_{stamp}.json"

        # Step 2: export labels → CSV.
        try:
            call_command(
                "export_at_risk_training_data",
                "--school", opts["school"],
                "--out", str(training_csv),
                stdout=self.stdout,
            )
        except CommandError as exc:
            self.stderr.write(self.style.ERROR(f"Label export failed: {exc}"))
            sys.exit(_EXIT_PIPELINE_ABORTED)

        if opts.get("skip_train"):
            self.stdout.write(self.style.SUCCESS(
                f"Dry run complete: training CSV at {training_csv}"
            ))
            sys.exit(_EXIT_OK)

        # Step 3: train (subprocess — train_at_risk.py is a script, not a
        # Django management command).
        train_script = (
            Path(__file__).resolve().parents[3] / "ml" / "train_at_risk.py"
        )
        try:
            subprocess.run(  # shell-true-allow: only fixed-args list passed; no user input concatenated
                [sys.executable, str(train_script),
                 "--csv", str(training_csv),
                 "--out", str(candidate_joblib)],
                check=True,
            )
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            self.stderr.write(self.style.ERROR(f"Training failed: {exc}"))
            sys.exit(_EXIT_PIPELINE_ABORTED)

        # Step 4: evaluate against holdout (or synthetic).
        eval_args = [
            str(candidate_joblib),
            "--json", str(eval_report),
            "--min-roc-auc", str(opts["min_roc_auc"]),
            "--min-average-precision", str(opts["min_average_precision"]),
        ]
        if opts.get("holdout_csv"):
            eval_args += ["--csv", opts["holdout_csv"]]
        try:
            call_command("evaluate_at_risk_model", *eval_args, stdout=self.stdout)
        except CommandError as exc:
            self.stderr.write(self.style.ERROR(f"Holdout gate failed: {exc}"))
            sys.exit(_EXIT_PIPELINE_ABORTED)

        # Step 5: register as candidate. The version string is
        # date-stamped so consecutive runs don't collide.
        version = f"at_risk_{opts['school']}_{stamp}"
        try:
            call_command(
                "register_at_risk_artifact",
                str(candidate_joblib),
                "--model-version", version,
                "--registered-by-username", opts["operator_username"],
                "--training-csv", str(training_csv),
                "--eval-json", str(eval_report),
                "--notes",
                f"Auto-registered by retrain_at_risk_pipeline at {stamp}",
                stdout=self.stdout,
            )
        except CommandError as exc:
            self.stderr.write(self.style.ERROR(f"Registration failed: {exc}"))
            sys.exit(_EXIT_PIPELINE_ABORTED)

        summary = {
            "version": version,
            "training_csv": str(training_csv),
            "candidate_joblib": str(candidate_joblib),
            "eval_report": str(eval_report),
        }
        self.stdout.write(self.style.SUCCESS(
            "Pipeline complete (candidate registered): " + json.dumps(summary)
        ))
        sys.exit(_EXIT_OK)
