"""AI model promotion-readiness verifier.

12-pillar audit P8 follow-up. The CANDIDATE -> PRODUCTION decision on the
at-risk model registry is intentionally operator-driven (per memory
project_ai_ml_wave_2_shadow_scoring_v2_93), but until this command
existed, "is the candidate ready?" was a human judgment with no
machine-checked signal.

This command computes a readiness verdict from the existing
``AtRiskShadowRun`` table — no new schema. The verdict is one of:

* ``no-candidate`` -- no CANDIDATE artifact registered.
* ``no-shadow-evidence`` -- candidate exists but no shadow runs.
* ``insufficient-sample`` -- shadow runs total fewer students than
  ``--min-students`` (default 100).
* ``failing-agreement`` -- aggregate agreement is below ``--min-agreement``
  (default 0.85).
* ``failing-psi`` -- score-distribution PSI exceeds ``--max-psi`` (default 0.25).
* ``ready`` -- all thresholds clear.

The operator still pulls the promotion trigger via the admin action;
this command just answers "should I be looking at this row today?".

Usage::

    python manage.py verify_ai_promotion_readiness
    python manage.py verify_ai_promotion_readiness --json
    python manage.py verify_ai_promotion_readiness --strict   # exit 1 if not ready
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from django.core.management.base import BaseCommand


@dataclass(frozen=True)
class Readiness:
    verdict: str
    candidate_version: str | None
    production_version: str | None
    shadow_run_count: int
    students_scored: int
    agreement_pct: float | None
    psi_score_distribution: float | None
    band_change_pct: float | None
    reasons: list[str]

    @property
    def ready(self) -> bool:
        return self.verdict == "ready"


def _aggregate(shadow_runs) -> tuple[int, float | None, float | None, float | None]:
    """Return (students_scored, weighted_agreement, weighted_psi, band_change_pct).

    Agreement and PSI are weighted by students_scored so a single tiny
    run can't skew the verdict. Returns None for the rate fields when
    the denominator is zero.
    """
    total_students = 0
    agreement_numerator = 0.0
    psi_numerator = 0.0
    band_changes = 0
    psi_weight = 0
    agreement_weight = 0
    for run in shadow_runs:
        n = run.students_scored or 0
        total_students += n
        band_changes += run.band_changes or 0
        if n and run.agreement_pct is not None:
            agreement_numerator += run.agreement_pct * n
            agreement_weight += n
        if n and run.psi_score_distribution is not None:
            psi_numerator += run.psi_score_distribution * n
            psi_weight += n
    agreement = (
        agreement_numerator / agreement_weight if agreement_weight else None
    )
    psi = psi_numerator / psi_weight if psi_weight else None
    band_change_pct = (
        band_changes / total_students if total_students else None
    )
    return total_students, agreement, psi, band_change_pct


def compute_readiness(
    *,
    min_students: int = 100,
    min_agreement: float = 0.85,
    max_psi: float = 0.25,
) -> Readiness:
    """Compute readiness without printing — also imported by tests."""
    # Imported lazily so the file imports cleanly even when Django is
    # not configured (e.g. linting).
    from apps.analytics.models_ml_registry import (
        AtRiskModelArtifact,
        AtRiskShadowRun,
    )

    production = AtRiskModelArtifact.current_production()
    candidate = (
        AtRiskModelArtifact.objects.filter(
            status=AtRiskModelArtifact.Status.CANDIDATE
        )
        .order_by("-registered_at")
        .first()
    )

    if candidate is None:
        return Readiness(
            verdict="no-candidate",
            candidate_version=None,
            production_version=production.model_version if production else None,
            shadow_run_count=0,
            students_scored=0,
            agreement_pct=None,
            psi_score_distribution=None,
            band_change_pct=None,
            reasons=["no CANDIDATE artifact registered"],
        )

    shadow_runs = list(
        AtRiskShadowRun.objects.filter(
            candidate_artifact=candidate,
            outcome=AtRiskShadowRun.Outcome.OK,
        )
    )
    students_scored, agreement, psi, band_change_pct = _aggregate(shadow_runs)

    if not shadow_runs:
        return Readiness(
            verdict="no-shadow-evidence",
            candidate_version=candidate.model_version,
            production_version=production.model_version if production else None,
            shadow_run_count=0,
            students_scored=0,
            agreement_pct=None,
            psi_score_distribution=None,
            band_change_pct=None,
            reasons=[
                "no AtRiskShadowRun rows with outcome=ok for this candidate",
                "run `python manage.py score_shadow_at_risk` against representative tenants",
            ],
        )

    reasons: list[str] = []
    if students_scored < min_students:
        reasons.append(
            f"students_scored={students_scored} below threshold {min_students}"
        )
    if agreement is not None and agreement < min_agreement:
        reasons.append(
            f"agreement_pct={agreement:.4f} below threshold {min_agreement:.2f}"
        )
    if psi is not None and psi > max_psi:
        reasons.append(
            f"psi_score_distribution={psi:.4f} above threshold {max_psi:.2f}"
        )

    if not reasons:
        verdict = "ready"
        reasons = [
            f"agreement={agreement:.4f}" if agreement is not None else "agreement=n/a",
            f"psi={psi:.4f}" if psi is not None else "psi=n/a",
            f"students={students_scored}",
        ]
    # Verdict picks ONE label by severity ladder: insufficient-sample is
    # most fundamental (small N makes the other two metrics untrustworthy),
    # then agreement (the core "do the models predict the same thing?"
    # signal), then PSI (a distribution-shape sanity check). The `reasons`
    # list above still reports every failing threshold, so the operator
    # sees all failures even though the verdict label highlights the most
    # actionable one.
    elif students_scored < min_students:
        verdict = "insufficient-sample"
    elif agreement is not None and agreement < min_agreement:
        verdict = "failing-agreement"
    else:
        verdict = "failing-psi"

    return Readiness(
        verdict=verdict,
        candidate_version=candidate.model_version,
        production_version=production.model_version if production else None,
        shadow_run_count=len(shadow_runs),
        students_scored=students_scored,
        agreement_pct=agreement,
        psi_score_distribution=psi,
        band_change_pct=band_change_pct,
        reasons=reasons,
    )


class Command(BaseCommand):
    help = "Compute CANDIDATE -> PRODUCTION promotion readiness for the at-risk model registry."

    def add_arguments(self, parser):
        parser.add_argument("--min-students", type=int, default=100)
        parser.add_argument("--min-agreement", type=float, default=0.85)
        parser.add_argument("--max-psi", type=float, default=0.25)
        parser.add_argument("--json", action="store_true")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero when verdict is not 'ready'.",
        )

    def handle(self, *args, **options):
        readiness = compute_readiness(
            min_students=options["min_students"],
            min_agreement=options["min_agreement"],
            max_psi=options["max_psi"],
        )

        if options["json"]:
            payload = asdict(readiness)
            payload["ready"] = readiness.ready
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(
                f"AI promotion readiness: verdict={readiness.verdict} "
                f"candidate={readiness.candidate_version or '<none>'} "
                f"production={readiness.production_version or '<none>'}"
            )
            if readiness.shadow_run_count:
                agreement_disp = (
                    f"{readiness.agreement_pct:.4f}"
                    if readiness.agreement_pct is not None
                    else "n/a"
                )
                psi_disp = (
                    f"{readiness.psi_score_distribution:.4f}"
                    if readiness.psi_score_distribution is not None
                    else "n/a"
                )
                self.stdout.write(
                    f"  shadow_runs={readiness.shadow_run_count} "
                    f"students={readiness.students_scored} "
                    f"agreement={agreement_disp} psi={psi_disp}"
                )
            for reason in readiness.reasons:
                self.stdout.write(f"  - {reason}")

        if options["strict"] and not readiness.ready:
            # Translate non-ready verdicts to exit 1 so the operator's CI
            # / runbook can detect them. Django's BaseCommand handles
            # non-zero exits via SystemExit.
            raise SystemExit(1)
