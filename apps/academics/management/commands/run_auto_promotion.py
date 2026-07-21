"""
Plan II: Year-end auto-promotion job.

Moves students from a source academic year to the target year, HONOURING
``reports.PromotionRule``. Program item 2.2.

What changed (and why the old shape was wrong): this command used to run

    student.academic_year = to_year
    student.classroom = m.target_classroom
    student.save(update_fields=[...])

for every student in the source year. That did three damaging things at once —
it overwrote last year's placement (so there was no academic history), it made
*repeating a year* impossible to express, and it never looked at PromotionRule,
so a failing student advanced identically to a passing one.

It now writes an ``people.Enrollment`` per student per year: the prior year's
enrollment is CLOSED with a recorded outcome and a new one is OPENED. The
student row is still kept in step as a projection, so every existing reader of
``student.classroom`` is unaffected.

Usage: python manage.py run_auto_promotion --from-year=2024/2025 --to-year=2025/2026 \
        [--school=UUID] [--dry-run] [--no-data-policy=promote|retain|skip]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.academics.models import AcademicYear, ClassroomPromotionMapping
from apps.people.enrollment_services import (
    NO_DATA_POLICIES,
    NO_DATA_PROMOTE,
    promote_cohort,
)
from apps.schools.rls_context import rls_bypass, rls_school


class Command(BaseCommand):
    help = (
        "Plan II: Auto-promote students from one academic year to the next, "
        "honouring PromotionRule (retention and conditional promotion included)."
    )

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
        parser.add_argument(
            "--no-data-policy",
            type=str,
            default=NO_DATA_PROMOTE,
            choices=list(NO_DATA_POLICIES),
            help=(
                "What to do with a student who has no marks or whose scope has "
                "no PromotionRule. Default 'promote' reproduces the behaviour "
                "from before promotion rules were honoured, so a school that "
                "has configured nothing sees no change."
            ),
        )

    def handle(self, *args, **options):
        school_id = options.get("school")
        # FORCE RLS (schools 0048): pin to one school when --school is given;
        # otherwise bypass so an operator-initiated cross-tenant run can proceed.
        ctx = rls_school(school_id) if school_id else rls_bypass()
        with ctx:
            self._run(options)

    def _run(self, options):
        from_name = (options["from_year"] or "").strip()
        to_name = (options["to_year"] or "").strip()
        school_id = options.get("school")
        dry_run = options.get("dry_run", False)
        no_data_policy = options.get("no_data_policy") or NO_DATA_PROMOTE

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

        def report(student, decision, enrollment, skip_reason):
            if skip_reason:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped {student.student_code} {student.get_full_name()}: "
                        f"{skip_reason}"
                    )
                )
                return
            verb = "Would place" if dry_run else "Placed"
            where = enrollment.classroom.name if enrollment else "(dry run)"
            self.stdout.write(
                f"{verb}: {student.student_code} {student.get_full_name()} "
                f"-> {where} ({to_name}) [{decision.outcome}]"
            )

        result = promote_cohort(
            from_year,
            to_year,
            school_id=school_id,
            mappings=mappings,
            no_data_policy=no_data_policy,
            dry_run=dry_run,
            on_student=report,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Promotion complete: "
                f"{result.promoted} promoted, "
                f"{result.conditionally_promoted} conditionally promoted, "
                f"{result.retained} retained, "
                f"{result.skipped} skipped."
                + (" (dry run)" if dry_run else "")
            )
        )
        if result.skipped_reasons:
            for reason, count in sorted(result.skipped_reasons.items()):
                self.stdout.write(f"  skipped[{reason}] = {count}")
