"""US Ed-Fi JSON — the increment-1 reference ministry format.

Assembles an Ed-Fi-shaped interchange document for one school + academic year by
REUSING the existing per-record Ed-Fi mappers in ``apps.interop.edfi.adapter``
(``student_to_edfi`` / ``student_school_association_to_edfi`` /
``evaluation_to_edfi_grade``). This module writes NO second mapper.

Those mappers take ORM *instances* (a ``StudentProfile`` / an ``Evaluation`` +
the ``School``), not dict rows — verified against the adapter and its live caller
``apps/api/edfi_views.py`` — so we resolve the instances they were written for,
tenant-scoped by school + academic_year exactly as ``emis.services.EMISExportService``
scopes its own reads (``StudentProfile.filter(school=, academic_year=, is_active=True)``
and ``Evaluation.filter(school=, academic_year=)``), then serialize to stable JSON.
"""

from __future__ import annotations

import json
import logging
from typing import Any

# Module-level import so a broken mapper import surfaces as ImportError on
# package import (the brief's contract) rather than being silently swallowed.
from apps.interop.edfi.adapter import (
    evaluation_to_edfi_grade,
    student_school_association_to_edfi,
    student_to_edfi,
)

from .base import MinistryFormatSerializer, register_ministry_format

logger = logging.getLogger(__name__)


@register_ministry_format
class EdFiJsonSerializer(MinistryFormatSerializer):
    """Serialize a school's students, enrollments, and grades as an Ed-Fi JSON document."""

    format_key = "us-edfi-json"
    country_code = "US"
    content_type = "application/json"
    file_extension = "json"
    description = "US Ed-Fi students / studentSchoolAssociations / grades interchange (JSON)."

    def serialize(self, school: Any, academic_year: Any, term: Any = None) -> str:
        students = self._students(school, academic_year)
        evaluations = self._evaluations(school, academic_year, term)

        student_resources: list[dict] = []
        association_resources: list[dict] = []
        grade_resources: list[dict] = []
        skipped = 0

        for student in students:
            # Per-record isolation: one bad row must never abort the whole export.
            # Broad Exception is deliberate — any mapper failure (missing attr, bad
            # value, ...) skips that single record and is counted, never raised.
            try:
                student_resources.append(student_to_edfi(student, school))
            except Exception:
                skipped += 1
                logger.warning(
                    "edfi student mapping skipped student pk=%s", getattr(student, "pk", "?")
                )
            try:
                association_resources.append(
                    student_school_association_to_edfi(student, school)
                )
            except Exception:
                skipped += 1
                logger.warning(
                    "edfi association mapping skipped student pk=%s", getattr(student, "pk", "?")
                )

        for evaluation in evaluations:
            try:
                grade = evaluation_to_edfi_grade(evaluation, school)
            except Exception:
                skipped += 1
                logger.warning(
                    "edfi grade mapping skipped evaluation pk=%s", getattr(evaluation, "pk", "?")
                )
                continue
            # The mapper returns {} for an evaluation with no resolvable student.
            if grade:
                grade_resources.append(grade)

        if skipped:
            logger.info("edfi serialize skipped %s unmappable record(s)", skipped)

        document = {
            "students": student_resources,
            "studentSchoolAssociations": association_resources,
            "grades": grade_resources,
        }
        # sort_keys => deterministic byte output (stable diffs / idempotent uploads).
        return json.dumps(document, sort_keys=True, indent=2, default=str)

    @staticmethod
    def _students(school: Any, academic_year: Any) -> list:
        from apps.people.models import StudentProfile

        return list(
            StudentProfile.objects.filter(
                school=school,
                academic_year=academic_year,
                is_active=True,
            )
            .select_related("user", "classroom")
            .order_by("last_name", "first_name")
        )

    @staticmethod
    def _evaluations(school: Any, academic_year: Any, term: Any) -> list:
        from apps.evals.models import Evaluation

        qs = Evaluation.objects.filter(school=school, academic_year=academic_year)
        if term is not None:
            qs = qs.filter(term=term)
        return list(qs.select_related("student", "subject_assignment").order_by("pk"))
