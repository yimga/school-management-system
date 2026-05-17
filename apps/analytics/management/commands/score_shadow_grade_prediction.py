"""Shadow scoring for grade-prediction: production vs candidate.

Mirrors `score_shadow_at_risk`. For each (active student × enrolled
subject) within the open term, scores with both production and candidate
artifacts, writes `GradePredictionShadowComparison` rows, aggregates
into `GradePredictionShadowRun`.

Decision metric is `mean_abs_delta` + `bias` (mean signed delta) rather
than agreement_pct — regression doesn't have a band-change concept.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.analytics.ml.grade_prediction_model import predict_grade_with_artifact
from apps.analytics.models import (
    GradePredictionModelArtifact,
    GradePredictionShadowComparison,
    GradePredictionShadowRun,
)
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.score_shadow_grade_prediction")


class Command(BaseCommand):
    help = "Compare production vs candidate grade-prediction artifacts per student×subject."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True)
        parser.add_argument("--candidate-version", default=None)
        parser.add_argument("--limit", type=int, default=None)

    def handle(self, *args, **opts):
        try:
            school = School.objects.get(slug=opts["school"])
        except School.DoesNotExist as exc:
            raise CommandError(f"No school '{opts['school']}'.") from exc

        production = GradePredictionModelArtifact.current_production()
        candidate = self._resolve_candidate(opts.get("candidate_version"))

        if not production or not candidate:
            run = GradePredictionShadowRun.objects.create(
                school=school,
                production_artifact=production or self._placeholder(),
                candidate_artifact=candidate or self._placeholder(),
                outcome=GradePredictionShadowRun.Outcome.SKIPPED,
                error_summary="Missing production or candidate artifact.",
                finished_at=timezone.now(),
            )
            self.stdout.write(
                f"Skipped — no {'production' if not production else 'candidate'}."
            )
            return

        if production.pk == candidate.pk:
            raise CommandError(
                "Production and candidate point to the same artifact."
            )

        run = GradePredictionShadowRun.objects.create(
            school=school,
            production_artifact=production,
            candidate_artifact=candidate,
        )
        try:
            self._populate(run, school, production, candidate, opts.get("limit"))
        except Exception as exc:  # noqa: BLE001 — must persist failure for telemetry
            run.outcome = GradePredictionShadowRun.Outcome.FAILED
            run.error_summary = str(exc)[:5000]
            run.finished_at = timezone.now()
            run.save(update_fields=["outcome", "error_summary", "finished_at"])
            raise

    def _resolve_candidate(self, version):
        if version:
            try:
                return GradePredictionModelArtifact.objects.get(model_version=version)
            except GradePredictionModelArtifact.DoesNotExist as exc:
                raise CommandError(
                    f"No grade-prediction artifact '{version}'."
                ) from exc
        return GradePredictionModelArtifact.objects.filter(
            status=GradePredictionModelArtifact.Status.CANDIDATE,
        ).order_by("-registered_at").first()

    def _placeholder(self):
        return GradePredictionModelArtifact.objects.order_by("-registered_at").first()

    def _populate(self, run, school, production, candidate, limit):
        from apps.academics.models import SubjectAssignment, Term
        from apps.people.models import StudentProfile

        today = timezone.now().date()
        term = Term.objects.filter(
            start_date__lte=today, end_date__gte=today,
        ).order_by("-start_date").first()
        if term is None:
            run.outcome = GradePredictionShadowRun.Outcome.SKIPPED
            run.error_summary = "No open term."
            run.finished_at = timezone.now()
            run.save(update_fields=["outcome", "error_summary", "finished_at"])
            return

        # tenant-isolation-allow: SubjectAssignment scoped via term FK (tenant-bound)
        assignments = list(
            SubjectAssignment.objects.filter(term=term)
            .select_related("classroom", "subject")
        )
        deltas: list[float] = []
        rows: list[GradePredictionShadowComparison] = []
        compared = 0
        for sa in assignments:
            classroom = sa.classroom
            subject = sa.subject
            # tenant-isolation-allow: classroom scoped via school=
            students = StudentProfile.objects.filter(
                school=school, classroom=classroom, is_active=True,
            )
            if limit:
                students = students[:limit]
            for student in students:
                p = predict_grade_with_artifact(
                    student, subject, term, production.artifact_path,
                )
                c = predict_grade_with_artifact(
                    student, subject, term, candidate.artifact_path,
                )
                if p is None or c is None:
                    continue
                rows.append(GradePredictionShadowComparison(
                    run=run, student=student, subject=subject,
                    production_grade=p, candidate_grade=c,
                    grade_delta=c - p,
                ))
                deltas.append(c - p)
                compared += 1

        if rows:
            GradePredictionShadowComparison.objects.bulk_create(rows, batch_size=500)

        if deltas:
            abs_d = sorted(abs(d) for d in deltas)
            mid = len(abs_d) // 2
            median = (
                abs_d[mid] if len(abs_d) % 2
                else (abs_d[mid - 1] + abs_d[mid]) / 2
            )
            p95_idx = max(0, int(round(0.95 * (len(abs_d) - 1))))
            run.rows_compared = compared
            run.mean_abs_delta = sum(abs_d) / len(abs_d)
            run.median_abs_delta = median
            run.p95_abs_delta = abs_d[p95_idx]
            run.bias = sum(deltas) / len(deltas)
        run.outcome = GradePredictionShadowRun.Outcome.OK
        run.finished_at = timezone.now()
        run.save()
        self.stdout.write(self.style.SUCCESS(
            f"Shadow grade-prediction complete: compared={compared} "
            f"mean|Δ|={run.mean_abs_delta} bias={run.bias}"
        ))
