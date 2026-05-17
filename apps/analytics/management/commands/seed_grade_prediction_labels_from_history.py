"""Backfill GradePredictionLabel from finalized Evaluation rows.

Treats `final_score` (or `exam_score` when final_score is null) as
the actual end-of-term grade and creates one `GradePredictionLabel`
per (student, subject, academic_year, term) where:

  * the Evaluation has a non-null score above the configured floor, AND
  * the (student, subject, year, term) is not already labelled.

Idempotent via the unique constraint on the four scoping fields.

Lets operators train a v1 grade-prediction model on real historical
data *immediately* — without waiting a term for the labelling UI to
fill up.

Usage:
    python manage.py seed_grade_prediction_labels_from_history
    python manage.py seed_grade_prediction_labels_from_history \
        --school <slug> --min-score 0 --labeled-by-username admin
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from apps.accounts.models import User
from apps.analytics.models import GradePredictionLabel
from apps.schools.models import School

logger = logging.getLogger(
    "apps.analytics.commands.seed_grade_prediction_labels_from_history"
)


class Command(BaseCommand):
    help = (
        "Backfill GradePredictionLabel rows from existing Evaluation history."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school", default=None, help="Slug to scope to.")
        parser.add_argument(
            "--labeled-by-username", required=True,
            help="User attributed as labeler (audit field).",
        )
        parser.add_argument(
            "--min-score", type=float, default=0.0,
            help="Only seed labels where score >= this (default: 0, all).",
        )
        parser.add_argument(
            "--academic-year", default=None,
            help="Restrict to one academic year ID.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Count what would be seeded; do not write rows.",
        )

    def handle(self, *args, **opts):
        from apps.evals.models import Evaluation

        try:
            operator = User.objects.get(username=opts["labeled_by_username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f"No user '{opts['labeled_by_username']}'."
            ) from exc

        schools_qs = School.objects.filter(is_active=True)
        if opts.get("school"):
            schools_qs = schools_qs.filter(slug=opts["school"])
            if not schools_qs.exists():
                raise CommandError(f"No active school '{opts['school']}'.")

        total_created = total_skipped = total_no_score = 0
        for school in schools_qs:
            # tenant-isolation-allow: scoped via school= below
            eval_qs = Evaluation.objects.filter(
                school=school,
            ).select_related(
                "academic_year", "term", "subject_assignment__subject",
            )
            if opts.get("academic_year"):
                eval_qs = eval_qs.filter(academic_year_id=opts["academic_year"])

            for ev in eval_qs.iterator(chunk_size=500):
                score = self._resolve_score(ev)
                if score is None:
                    total_no_score += 1
                    continue
                if score < opts["min_score"]:
                    total_skipped += 1
                    continue
                subject = getattr(
                    getattr(ev, "subject_assignment", None), "subject", None,
                )
                if subject is None:
                    total_skipped += 1
                    continue
                if opts.get("dry_run"):
                    total_created += 1
                    continue
                try:
                    _, was_created = GradePredictionLabel.objects.get_or_create(
                        student=ev.student,
                        subject=subject,
                        academic_year=ev.academic_year,
                        term=ev.term,
                        defaults={
                            "school": school,
                            "actual_grade": score,
                            "labeled_by": operator,
                            "notes": (
                                "Auto-seeded from Evaluation row id="
                                f"{ev.pk} (final_score/exam_score)."
                            ),
                        },
                    )
                except IntegrityError:
                    total_skipped += 1
                    continue
                if was_created:
                    total_created += 1
                else:
                    total_skipped += 1
        verb = "Would create" if opts.get("dry_run") else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {total_created} label(s); "
            f"skipped {total_skipped} existing/below-min; "
            f"{total_no_score} evaluation(s) had no usable score."
        ))

    @staticmethod
    def _resolve_score(evaluation):
        """Final-score-or-exam-score fallback. Both are floats 0-100 in this
        schema; treat 0 as 'no signal' for backfill purposes only when
        it's clearly a placeholder. We accept 0 here and let --min-score
        filter explicitly."""
        for attr in ("final_score", "exam_score"):
            value = getattr(evaluation, attr, None)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None
