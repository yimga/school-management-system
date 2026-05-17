"""Index every active student record into the embedding store.

Run nightly after `compute_nightly_risk` so the search index reflects
the latest risk band on each student card. Idempotent — same text →
same hash → update_or_create keeps the row count stable.

Per-tenant scoping is implicit: each student row writes its school_id
into the embedding row, and `semantic_search.search_students` filters
on it. The command itself doesn't need a --school arg, but supports
one for backfill / smoke tests.
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand

from apps.analytics.semantic_search import index_student
from apps.platform_runtime.structured_logging import log_exception_with_context
from apps.schools.models import School

logger = logging.getLogger("apps.analytics.commands.build_student_embeddings")

_INDEX_ERRORS = (ImportError, AttributeError, TypeError, ValueError)


class Command(BaseCommand):
    help = "Compute + persist semantic-search embeddings for every active student."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school", type=str,
            help="Scope to one school (UUID or slug); omit for all active.",
        )
        parser.add_argument(
            "--limit", type=int, default=None,
            help="Cap students per school (smoke tests).",
        )

    def handle(self, *args, **options):
        from apps.people.models import StudentProfile

        schools = School.objects.filter(is_active=True)
        if options.get("school"):
            schools = schools.filter(slug=options["school"])
            if not schools.exists():
                schools = School.objects.filter(id=options["school"])
        if not schools.exists():
            self.stdout.write("No schools to process.")
            return
        indexed = 0
        failed = 0
        for school in schools:
            students = StudentProfile.objects.filter(
                school=school, is_active=True,
            )
            if options.get("limit"):
                students = students[:options["limit"]]
            for student in students:
                try:
                    ok = index_student(student)
                except _INDEX_ERRORS as exc:
                    log_exception_with_context(
                        "build_student_embeddings: index failed",
                        school_id=str(school.id),
                        extra={"student_id": str(student.id), "error": str(exc)},
                    )
                    ok = False
                if ok:
                    indexed += 1
                else:
                    failed += 1
        self.stdout.write(self.style.SUCCESS(
            f"Indexed {indexed} student(s); {failed} skipped/failed."
        ))
