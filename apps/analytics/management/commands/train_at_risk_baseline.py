"""Wave K3 — train a baseline at-risk ML artifact.

Wraps `apps.analytics.ml.train_at_risk` as a Django management command so
operators can train the synthetic baseline without leaving the manage.py
surface. The artifact is written to ``settings.AT_RISK_MODEL_DIR`` (which
defaults to ``BASE_DIR/var/at_risk``) as ``at_risk_v1.joblib``.

After this command succeeds, `predict_at_risk` will automatically load
the artifact on next call (process-level joblib cache reset via
``--reload`` on `score_student_risk`).

Usage:
  python manage.py train_at_risk_baseline                 # synthetic, n=5000
  python manage.py train_at_risk_baseline --samples 20000
  python manage.py train_at_risk_baseline --csv real.csv
  python manage.py train_at_risk_baseline --out /tmp/m.joblib --no-write-clear-cache

Honest scoping: the synthetic dataset is reasonable for SHAPE validation
(it confirms the pipeline writes a callable artifact at the right path
and that the inference path flips from heuristic → ml-artifact). A
production-quality model still requires labeled historical at-risk
outcomes. Use `--csv` once that data exists.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Train (and persist) the baseline at-risk classifier artifact."

    def add_arguments(self, parser):
        parser.add_argument(
            "--samples", type=int, default=5000,
            help="Synthetic sample count when --csv is not supplied.",
        )
        parser.add_argument(
            "--seed", type=int, default=42,
            help="Reproducibility seed for synthetic generation and train/test split.",
        )
        parser.add_argument(
            "--csv", type=str, default=None,
            help="Path to a labeled CSV (FEATURE_ORDER columns + 'label').",
        )
        parser.add_argument(
            "--out", type=str, default=None,
            help=(
                "Override output path. Defaults to "
                "settings.AT_RISK_MODEL_DIR/at_risk_v1.joblib"
            ),
        )
        parser.add_argument(
            "--no-write", action="store_true",
            help="Run end-to-end training and report metrics but skip writing the artifact.",
        )
        parser.add_argument(
            "--clear-cache", action="store_true",
            help=(
                "Also reset the in-process joblib cache in "
                "apps.analytics.ml.at_risk_model so the next predict_at_risk "
                "call picks up the freshly-written artifact."
            ),
        )

    def handle(self, *args, **opts):
        out = opts.get("out") or os.path.join(
            getattr(settings, "AT_RISK_MODEL_DIR", "var/at_risk"),
            "at_risk_v1.joblib",
        )
        Path(out).parent.mkdir(parents=True, exist_ok=True)

        # Delegate to the existing pure-Python entry point. Soft-fails if
        # sklearn/joblib are missing (exit code 2 from train_at_risk.main).
        from apps.analytics.ml.train_at_risk import main as train_main

        argv = [
            "--samples", str(opts["samples"]),
            "--seed", str(opts["seed"]),
        ]
        if opts.get("csv"):
            argv += ["--csv", opts["csv"]]
        if opts.get("no_write"):
            argv += ["--no-write"]
        else:
            argv += ["--out", out]

        # train_at_risk.main configures its own logging on __main__ but when
        # called as a function it inherits the Django logging config — that's
        # fine, the messages still reach stderr.
        rc = train_main(argv)
        if rc != 0:
            raise CommandError(
                f"train_at_risk exited with code {rc}. Install scikit-learn + joblib "
                "or check the CSV schema (FEATURE_ORDER columns + 'label')."
            )

        if not opts.get("no_write"):
            self.stdout.write(self.style.SUCCESS(f"wrote artifact: {out}"))
            self.stdout.write(
                "set AT_RISK_MODEL_PATH or place the artifact at "
                f"{getattr(settings, 'AT_RISK_MODEL_DIR', 'var/at_risk')}/at_risk_v1.joblib "
                "for auto-discovery."
            )

        if opts.get("clear_cache"):
            try:
                from apps.analytics.ml import at_risk_model

                at_risk_model._MODEL_CACHE.clear()
                self.stdout.write("cleared in-process at_risk_model cache.")
            except (ImportError, AttributeError) as exc:
                logger.warning("could not clear at_risk_model cache: %s", exc)
