"""
Backfill precomputed search_index columns (Google pillar hygiene).

Run after deploy or restore:
  python manage.py backfill_search_indexes
  python manage.py backfill_search_indexes --only students
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = "Backfill StudentProfile.search_index and PortalFeatureItem.search_index rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=("all", "students", "documents"),
            default="all",
            help="Limit backfill scope.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Bulk update batch size.",
        )

    def handle(self, *args, **options):
        only = options["only"]
        batch_size = max(50, int(options["batch_size"] or 500))
        if only in ("all", "students"):
            self._backfill_students(batch_size)
        if only in ("all", "documents"):
            self._backfill_documents(batch_size)
        self.stdout.write(self.style.SUCCESS("backfill_search_indexes: complete"))

    def _backfill_students(self, batch_size: int) -> None:
        from apps.people.models import StudentProfile
        from apps.people.student_search_index import build_student_search_index

        updated = 0
        batch: list[StudentProfile] = []
        for row in StudentProfile.objects.iterator(chunk_size=batch_size):
            row.search_index = build_student_search_index(row)
            batch.append(row)
            if len(batch) >= batch_size:
                with transaction.atomic():
                    StudentProfile.objects.bulk_update(batch, ["search_index"])
                updated += len(batch)
                batch = []
        if batch:
            with transaction.atomic():
                StudentProfile.objects.bulk_update(batch, ["search_index"])
            updated += len(batch)
        self.stdout.write(f"  students: {updated} search_index rows refreshed")

    def _backfill_documents(self, batch_size: int) -> None:
        from apps.portal.document_lifecycle import build_document_search_index
        from apps.portal.models import PortalFeatureItem

        updated = 0
        batch: list[PortalFeatureItem] = []
        for row in PortalFeatureItem.objects.iterator(chunk_size=batch_size):
            row.search_index = build_document_search_index(row)
            batch.append(row)
            if len(batch) >= batch_size:
                with transaction.atomic():
                    PortalFeatureItem.objects.bulk_update(batch, ["search_index"])
                updated += len(batch)
                batch = []
        if batch:
            with transaction.atomic():
                PortalFeatureItem.objects.bulk_update(batch, ["search_index"])
            updated += len(batch)
        self.stdout.write(f"  documents: {updated} search_index rows refreshed")
