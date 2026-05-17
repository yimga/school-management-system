"""Score every active student against BOTH production and a candidate
artifact; write per-student `AtRiskShadowComparison` rows and an
aggregate `AtRiskShadowRun` summary.

Resolves the candidate as the most-recent `status=candidate` registered
artifact unless `--candidate-version` is passed explicitly. Skips
cleanly when no production or no candidate exists (the typical day-zero
state — no error, just an `Outcome.SKIPPED` row so the operator can see
the loop is wired but waiting).

The intent is operator-evidence, not production-replacement: shadow
scores are NEVER written back to `RiskFactor`. They live in their own
table so the production read path stays clean.

Usage (cron-friendly):
    python manage.py score_shadow_at_risk --school <slug>
    python manage.py score_shadow_at_risk --school <slug> --candidate-version v2_q3
"""

from __future__ import annotations

import logging
import math
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.analytics.models import (
    AtRiskModelArtifact,
    AtRiskShadowComparison,
    AtRiskShadowRun,
)
from apps.analytics.ml.at_risk_model import predict_with_artifact
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.score_shadow_at_risk")

_RED_BAND_MIN = 80.0
_AMBER_BAND_MIN = 50.0
_PSI_BINS = 10
_PSI_BIN_WIDTH = 10  # 100 / _PSI_BINS — score domain is [0, 100]
_PSI_EPSILON = 1e-4


def _band(score: float) -> str:
    if score >= _RED_BAND_MIN:
        return "red"
    if score >= _AMBER_BAND_MIN:
        return "amber"
    return "green"


def _band_rank(band: str) -> int:
    """Higher rank = higher risk. Used to classify a change as promotion/demotion."""
    return {"green": 0, "amber": 1, "red": 2}.get(band, 0)


def _bin(score: float) -> int:
    if score >= _PSI_BINS * _PSI_BIN_WIDTH:
        return _PSI_BINS - 1
    if score <= 0:
        return 0
    return min(int(score // _PSI_BIN_WIDTH), _PSI_BINS - 1)


def _distribution(scores: list[float]) -> list[float]:
    if not scores:
        return [0.0] * _PSI_BINS
    counter = Counter()
    for s in scores:
        counter[_bin(s)] += 1
    return [counter.get(i, 0) / len(scores) for i in range(_PSI_BINS)]


def _psi(a: list[float], b: list[float]) -> float:
    psi = 0.0
    for ref, cur in zip(a, b):
        ref_p = max(ref, _PSI_EPSILON)
        cur_p = max(cur, _PSI_EPSILON)
        psi += (cur_p - ref_p) * math.log(cur_p / ref_p)
    return psi


class Command(BaseCommand):
    help = "Score active students against production AND candidate artifacts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", required=True,
            help="School slug to score.",
        )
        parser.add_argument(
            "--candidate-version", default=None,
            help="model_version of candidate artifact (default: most recent CANDIDATE row).",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Cap number of students scored (smoke tests).",
        )

    def handle(self, *args, **opts):
        try:
            school = School.objects.get(slug=opts["school"])
        except School.DoesNotExist as exc:
            raise CommandError(f"No school '{opts['school']}'.") from exc

        production = AtRiskModelArtifact.current_production()
        candidate = self._resolve_candidate(opts.get("candidate_version"))

        if not production or not candidate:
            run = AtRiskShadowRun.objects.create(
                school=school,
                production_artifact=production or self._placeholder_artifact(),
                candidate_artifact=candidate or self._placeholder_artifact(),
                outcome=AtRiskShadowRun.Outcome.SKIPPED,
                error_summary="Missing production or candidate artifact.",
                finished_at=timezone.now(),
            )
            self.stdout.write(
                f"Skipped — no {'production' if not production else 'candidate'}."
            )
            return

        if production.pk == candidate.pk:
            raise CommandError(
                "Production and candidate point to the same artifact; nothing to compare."
            )

        run = AtRiskShadowRun.objects.create(
            school=school,
            production_artifact=production,
            candidate_artifact=candidate,
        )
        try:
            self._populate(run, school, production, candidate, opts.get("limit"))
        except Exception as exc:  # noqa: BLE001 — must capture and persist failure for telemetry
            run.outcome = AtRiskShadowRun.Outcome.FAILED
            run.error_summary = str(exc)[:5000]
            run.finished_at = timezone.now()
            run.save(update_fields=["outcome", "error_summary", "finished_at"])
            raise

    def _resolve_candidate(self, version):
        if version:
            try:
                return AtRiskModelArtifact.objects.get(model_version=version)
            except AtRiskModelArtifact.DoesNotExist as exc:
                raise CommandError(
                    f"No registered artifact with model_version='{version}'."
                ) from exc
        return AtRiskModelArtifact.objects.filter(
            status=AtRiskModelArtifact.Status.CANDIDATE
        ).order_by("-registered_at").first()

    def _placeholder_artifact(self):
        """For the SKIPPED row we still need NOT NULL FKs. Use the most recent
        registered artifact in any state as a placeholder; if there's
        literally nothing in the registry, the SKIPPED row can't be
        written and we just log."""
        return AtRiskModelArtifact.objects.order_by("-registered_at").first()

    def _populate(self, run, school, production, candidate, limit):
        from apps.people.models import StudentProfile

        students = StudentProfile.objects.filter(
            school=school, is_active=True
        ).select_related("user")
        if limit:
            students = students[:limit]

        prod_scores: list[float] = []
        cand_scores: list[float] = []
        abs_deltas: list[float] = []
        band_changes = promotions = demotions = 0
        rows_to_create: list[AtRiskShadowComparison] = []
        scored = 0

        for student in students:
            p_score = predict_with_artifact(student, production.artifact_path)
            c_score = predict_with_artifact(student, candidate.artifact_path)
            if p_score is None or c_score is None:
                logger.warning(
                    "score_shadow_at_risk: skipping student=%s (one model returned None)",
                    student.pk,
                )
                continue
            p_band = _band(p_score)
            c_band = _band(c_score)
            changed = p_band != c_band
            rows_to_create.append(AtRiskShadowComparison(
                run=run,
                student=student,
                production_score=p_score,
                candidate_score=c_score,
                score_delta=c_score - p_score,
                production_band=p_band,
                candidate_band=c_band,
                band_changed=changed,
            ))
            prod_scores.append(p_score)
            cand_scores.append(c_score)
            abs_deltas.append(abs(c_score - p_score))
            if changed:
                band_changes += 1
                if _band_rank(c_band) > _band_rank(p_band):
                    promotions += 1
                else:
                    demotions += 1
            scored += 1

        if rows_to_create:
            AtRiskShadowComparison.objects.bulk_create(rows_to_create, batch_size=500)

        run.students_scored = scored
        run.band_changes = band_changes
        run.promotions = promotions
        run.demotions = demotions
        if scored:
            run.agreement_pct = 1.0 - (band_changes / scored)
            run.mean_abs_delta = sum(abs_deltas) / len(abs_deltas)
            ordered = sorted(abs_deltas)
            mid = len(ordered) // 2
            run.median_abs_delta = (
                ordered[mid]
                if len(ordered) % 2
                else (ordered[mid - 1] + ordered[mid]) / 2
            )
            p95_index = max(0, int(round(0.95 * (len(ordered) - 1))))
            run.p95_abs_delta = ordered[p95_index]
            run.psi_score_distribution = _psi(
                _distribution(prod_scores), _distribution(cand_scores)
            )
        run.finished_at = timezone.now()
        run.outcome = AtRiskShadowRun.Outcome.OK
        run.save()
        self.stdout.write(self.style.SUCCESS(
            f"Shadow run complete: scored={scored} agreement="
            f"{run.agreement_pct:.3f} band_changes={band_changes} "
            f"(promote={promotions} demote={demotions}) psi={run.psi_score_distribution:.4f}"
        ))
