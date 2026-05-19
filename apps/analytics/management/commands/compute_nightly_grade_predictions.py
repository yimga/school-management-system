"""Compute grade predictions for every (active student × enrolled subject)
within the currently-open term.

Mirrors `compute_nightly_risk`. Heuristic always runs; ML model
overrides when production artifact is loaded.

Idempotent: keyed update_or_create on (student, subject, academic_year,
term). Re-running on the same day overwrites the row.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import DatabaseError, OperationalError
from django.utils import timezone

from apps.analytics.ml.grade_prediction_model import predict_grade
from apps.analytics.models import GradePrediction
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.compute_nightly_grade_predictions")

_GRADE_PRED_ERRORS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    DatabaseError,
    OperationalError,
)


class Command(BaseCommand):
    help = "Compute and persist grade predictions for every active student × enrolled subject."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", type=str,
            help="School ID (UUID) to process; omit for all active schools.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Only print what would be written, do not save.",
        )

    def handle(self, *args, **options):
        school_id = options.get("school")
        dry_run = options.get("dry_run", False)
        schools = School.objects.filter(is_active=True)
        if school_id:
            schools = schools.filter(id=school_id)
        if not schools.exists():
            self.stdout.write("No schools to process.")
            return
        total = 0
        for school in schools:
            total += self._process_school(school, dry_run)
        self.stdout.write(self.style.SUCCESS(f"Wrote {total} grade prediction(s)."))

    def _process_school(self, school, dry_run):
        from apps.academics.models import (
            SubjectAssignment, Term,
        )
        from apps.people.models import StudentProfile

        today = timezone.now().date()
        try:
            term = Term.objects.filter(
                start_date__lte=today, end_date__gte=today,
            ).order_by("-start_date").first()
        except _GRADE_PRED_ERRORS:
            log_exception_with_context(
                "compute_nightly_grade_predictions: term lookup failed",
                school_id=str(school.id),
            )
            return 0
        if term is None:
            self.stdout.write(
                f"School {school.id}: no open term — skipping."
            )
            return 0

        try:
            assignments = list(
                SubjectAssignment.objects.filter(term=term)
                .select_related("classroom", "subject", "academic_year")
            )
        except _GRADE_PRED_ERRORS:
            log_exception_with_context(
                "compute_nightly_grade_predictions: assignment fetch failed",
                school_id=str(school.id),
            )
            return 0

        count = 0
        for sa in assignments:
            classroom = sa.classroom
            subject = sa.subject
            year = sa.academic_year
            # tenant-isolation-allow: classroom is tenant-bound; sa.classroom.school_id == school.id by construction
            try:
                students = list(
                    StudentProfile.objects.filter(
                        school=school,
                        classroom=classroom,
                        is_active=True,
                    )
                )
            except _GRADE_PRED_ERRORS:
                continue
            for student in students:
                payload = predict_grade(student, subject, term)
                if dry_run:
                    self.stdout.write(
                        f"  Would write: student={student.id} subject={subject.id} "
                        f"term={term.id} predicted={payload['predicted_grade']}"
                    )
                    count += 1
                    continue
                try:
                    GradePrediction.objects.update_or_create(
                        student=student,
                        subject=subject,
                        academic_year=year,
                        term=term,
                        defaults={
                            "school": school,
                            "predicted_grade": payload["predicted_grade"],
                            "reason_summary": payload["reason_summary"][:500],
                            "confidence_low": payload["confidence_low"],
                            "confidence_high": payload["confidence_high"],
                            "model_version": payload["model_version"],
                        },
                    )
                    count += 1
                except _GRADE_PRED_ERRORS as exc:
                    log_exception_with_context(
                        "compute_nightly_grade_predictions: write failed",
                        school_id=str(school.id),
                        extra={"student_id": str(student.id), "error": str(exc)},
                    )
        return count
