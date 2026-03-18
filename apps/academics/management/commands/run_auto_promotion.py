"""
Plan II: Year-end auto-promotion job.
Moves students from source academic year to target year using ClassroomPromotionMapping.
Run after cloning the next year (clone_academic_year) and configuring mappings.
Usage: python manage.py run_auto_promotion --from-year=2024/2025 --to-year=2025/2026 [--school=UUID] [--dry-run]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.academics.models import AcademicYear, ClassroomPromotionMapping
from apps.people.models import StudentProfile


class Command(BaseCommand):
    help = "Plan II: Auto-promote students from one academic year to the next using ClassroomPromotionMapping."

    def add_arguments(self, parser):
        parser.add_argument(
            "--from-year",
            type=str,
            required=True,
            help="Source academic year name (e.g. 2024/2025)",
        )
        parser.add_argument(
            "--to-year",
            type=str,
            required=True,
            help="Target academic year name (e.g. 2025/2026)",
        )
        parser.add_argument(
            "--school",
            type=str,
            default=None,
            help="Optional: school UUID to limit promotion to one tenant",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only report what would be done",
        )

    def handle(self, *args, **options):
        from_name = (options["from_year"] or "").strip()
        to_name = (options["to_year"] or "").strip()
        school_id = options.get("school")
        dry_run = options.get("dry_run", False)

        from_year = AcademicYear.objects.filter(name=from_name).first()
        to_year = AcademicYear.objects.filter(name=to_name).first()
        if not from_year:
            self.stderr.write(self.style.ERROR(f"Academic year not found: {from_name}"))
            return
        if not to_year:
            self.stderr.write(self.style.ERROR(f"Academic year not found: {to_name}"))
            return

        qs = ClassroomPromotionMapping.objects.filter(
            source_year=from_year,
            target_year=to_year,
        ).select_related("source_classroom", "target_classroom")
        if school_id:
            qs = qs.filter(school_id=school_id)
        mappings = {m.source_classroom_id: m for m in qs}
        if not mappings:
            self.stdout.write(
                self.style.WARNING(
                    f"No promotion mappings from {from_name} to {to_name}. "
                    "Configure ClassroomPromotionMapping in admin."
                )
            )
            return

        students = StudentProfile.objects.filter(
            academic_year=from_year,
            classroom_id__in=mappings.keys(),
            is_active=True,
        ).select_related("classroom")
        if school_id:
            students = students.filter(school_id=school_id)

        promoted = 0
        skipped = 0
        for student in students:
            m = mappings.get(student.classroom_id)
            if not m or not m.target_classroom_id:
                skipped += 1
                continue
            if dry_run:
                self.stdout.write(
                    f"Would promote: {student.student_code} {student.get_full_name()} "
                    f"-> {m.target_classroom.name} ({to_name})"
                )
                promoted += 1
                continue
            with transaction.atomic():
                student.academic_year = to_year
                student.classroom = m.target_classroom
                student.save(update_fields=["academic_year", "classroom", "updated_at"])
                promoted += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Promotion complete: {promoted} promoted, {skipped} skipped (no mapping)."
                + (" (dry run)" if dry_run else "")
            )
        )
