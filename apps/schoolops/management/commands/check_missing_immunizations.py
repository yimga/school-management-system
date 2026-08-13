"""W24 — run the missing-immunization alert sweep for one school or all.

The concrete, runnable trigger so the feature is NOT inert: it resolves target
schools (``--school <slug|id>`` or every active school) and invokes
``apps.schoolops.tasks.check_missing_immunizations_task`` synchronously per
school. Beat scheduling and wiring into the rollover apply loop / intake form
are a deliberate follow-up, NOT this increment.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Sweep active students for missing required immunizations and raise "
        "guardian alerts. Targets one school (--school) or all active schools."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            dest="school",
            default=None,
            help="School slug or id. Omit to sweep all active schools.",
        )

    def handle(self, *args, **options):
        from apps.schoolops.tasks import check_missing_immunizations_task

        school_ref = options.get("school")
        if school_ref:
            school_id = self._resolve_school_id(school_ref)
            summary = check_missing_immunizations_task(school_id=str(school_id))
            self.stdout.write(
                self.style.SUCCESS(f"Immunization sweep ({school_ref}): {summary}")
            )
            return

        summary = check_missing_immunizations_task()
        self.stdout.write(
            self.style.SUCCESS(f"Immunization sweep (all active schools): {summary}")
        )

    @staticmethod
    def _resolve_school_id(ref):
        from django.core.exceptions import ValidationError

        from apps.schools.models import School

        school = School.objects.filter(slug=ref).first()
        if school is None:
            try:
                school = School.objects.filter(pk=ref).first()
            except (ValueError, TypeError, ValidationError):
                school = None
        if school is None:
            raise CommandError(f"School not found: {ref}")
        return school.pk
