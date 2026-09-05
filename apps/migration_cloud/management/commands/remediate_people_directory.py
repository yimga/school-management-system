"""Backfill enrollment SOT + guardian directory for one tenant.

Closes the gap after student import: ``StudentProfile`` placement exists but
``people.Enrollment`` / Guardians sidebar may still be empty until post-apply
hooks run or a repair pass syncs them.

Usage::

    manage.py remediate_people_directory --school gilead-tech --dry-run
    manage.py remediate_people_directory --school gilead-tech --apply
"""

from __future__ import annotations

from contextlib import contextmanager

from django.core.management.base import BaseCommand, CommandError

from apps.schools.models import School


@contextmanager
def _tenant_schema(school):
    from apps.migration_cloud.schema_binding import resolve_school_schema_name

    schema_name = (resolve_school_schema_name(school) or "").strip()
    if not schema_name:
        raise CommandError(
            f"No tenant schema bound to school {getattr(school, 'subdomain', school)!r}."
        )
    try:
        from django_tenants.utils import schema_context
    except ImportError:
        schema_context = None
    if schema_context is None:
        yield schema_name
        return
    from django.db import connection

    if not hasattr(connection, "set_schema"):
        yield schema_name
        return
    with schema_context(schema_name):
        yield schema_name


class Command(BaseCommand):
    help = (
        "Sync enrollments from student placements and promote parent DFV hints "
        "into the Guardian directory."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            required=True,
            help="School id, subdomain, or slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned work without writing.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Execute inside the tenant schema.",
        )

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["apply"]:
            raise CommandError("Pass --dry-run or --apply.")

        school = self._resolve_school(options["school"])
        dry_run = bool(options["dry_run"])

        with _tenant_schema(school):
            from apps.migration_cloud.enrollment_sync import sync_all_enrollments_for_school
            from apps.migration_cloud.guardian_directory import promote_unlinked_guardian_hints
            from apps.migration_cloud.student_placement_backfill import (
                backfill_student_classrooms_for_school,
            )

            classrooms = backfill_student_classrooms_for_school(school, dry_run=dry_run)
            self.stdout.write(f"Classroom placement backfill: {classrooms}")

            enrollment = sync_all_enrollments_for_school(school, dry_run=dry_run)
            self.stdout.write(f"Enrollment sync: {enrollment}")

            guardians = promote_unlinked_guardian_hints(school=school, dry_run=dry_run)
            self.stdout.write(f"Guardian directory: {guardians}")

    def _resolve_school(self, token: str) -> School:
        from apps.migration_cloud.management.school_resolution import (
            resolve_school_or_error,
        )

        return resolve_school_or_error(token)
