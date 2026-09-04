"""Backfill teaching graph closure for one tenant.

Provisions SubjectAssignment grid cells, TeacherAssignment RBAC links, and
materializes schedule DFV rows for schools that imported people/catalog before
the teaching-graph autopilot ran.

Usage::

    manage.py remediate_teaching_graph_closure --school gilead-tech --dry-run
    manage.py remediate_teaching_graph_closure --school gilead-tech --apply
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
        "Provision teaching grid + teacher RBAC links + schedule materialization "
        "for one school."
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
            help="Report planned closure without writing.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Execute closure inside the tenant schema.",
        )

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["apply"]:
            raise CommandError("Pass --dry-run or --apply.")

        school = self._resolve_school(options["school"])
        dry_run = bool(options["dry_run"])

        with _tenant_schema(school):
            from apps.migration_cloud.teaching_graph import (
                assess_teaching_graph_readiness,
                ensure_teaching_graph_closure,
            )

            before = assess_teaching_graph_readiness(school)
            self.stdout.write(f"Before: {before}")

            outcome = ensure_teaching_graph_closure(school, dry_run=dry_run)
            self.stdout.write(f"Closure: {outcome}")

            if not dry_run:
                after = assess_teaching_graph_readiness(school)
                self.stdout.write(f"After: {after}")

    def _resolve_school(self, token: str) -> School:
        from apps.migration_cloud.management.school_resolution import (
            resolve_school_or_error,
        )

        return resolve_school_or_error(token)
