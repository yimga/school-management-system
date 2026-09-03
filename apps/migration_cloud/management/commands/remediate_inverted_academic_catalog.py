"""Remediate inverted academic catalog rows for a single tenant.

Fixes the Cameroon TVET class of failure where subject master lists (TITLE /
DESCRIPTION / CATEGORY / coef) were mis-routed to ``Department`` + ``Specialty``,
or where teacher directory SPECIALTY tokens minted spurious departments.

Usage::

    manage.py remediate_inverted_academic_catalog --school gilead-tech --dry-run
    manage.py remediate_inverted_academic_catalog --school gilead-tech --apply
"""

from __future__ import annotations

from contextlib import contextmanager

from django.core.management.base import BaseCommand, CommandError

from apps.schools.models import School


@contextmanager
def _tenant_schema(school):
    """Enter the tenant schema for ``school`` (noop on single-schema backends)."""
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
        "Repair subject/specialty/department inversion for one school "
        "(Cameroon TVET mis-import)."
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
            help="Report planned repairs without writing.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Execute repairs inside a transaction.",
        )

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["apply"]:
            raise CommandError("Pass --dry-run or --apply.")

        school = self._resolve_school(options["school"])
        with _tenant_schema(school) as schema_name:
            from apps.migration_cloud.tenant_schema_readiness import (
                assess_tenant_schema_readiness,
            )

            self.stdout.write(f"Tenant schema: {schema_name}")
            readiness = assess_tenant_schema_readiness(
                schema_name, attempt_repair=True
            )
            if readiness.repaired_labels:
                self.stdout.write(
                    f"Schema columns repaired: {', '.join(readiness.repaired_labels)}"
                )
            if not readiness.ready:
                preview = ", ".join(readiness.missing_labels[:6])
                extra = ""
                if len(readiness.missing_labels) > 6:
                    extra = f" (+{len(readiness.missing_labels) - 6} more)"
                raise CommandError(
                    "Tenant schema is still missing columns after repair: "
                    f"{preview}{extra}. Run migrate_schemas for this tenant, then retry."
                )
            self._run_for_school(school, options)

    def _run_for_school(self, school, options) -> None:
        from apps.migration_cloud.catalog_repair import (
            apply_inverted_catalog_repair,
            plan_inverted_catalog_repair,
        )

        plan = plan_inverted_catalog_repair(school)

        self.stdout.write(f"School: {school.name} ({school.subdomain})")
        for key, val in plan.items():
            if key == "actionable":
                continue
            if isinstance(val, list):
                self.stdout.write(f"  {key}: {len(val)}")
                for item in val[:20]:
                    self.stdout.write(f"    - {item}")
                if len(val) > 20:
                    self.stdout.write(f"    ... +{len(val) - 20} more")
            else:
                self.stdout.write(f"  {key}: {val}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run — no changes written."))
            return

        if not plan.get("actionable"):
            self.stdout.write(self.style.SUCCESS("No phantom catalog rows detected."))
            return

        applied = apply_inverted_catalog_repair(school)
        self.stdout.write(
            self.style.SUCCESS(
                f"Applied: removed {applied['phantom_specialties_removed']} phantom specialties, "
                f"{applied['phantom_departments_removed']} phantom departments, "
                f"created/verified {applied['curriculum_links_created']} curriculum links."
            )
        )

    @staticmethod
    def _resolve_school(token: str):
        import uuid

        from django.db.models import Q

        filters = Q(subdomain=token) | Q(slug=token)
        try:
            uuid.UUID(str(token))
        except (ValueError, TypeError, AttributeError):
            pass
        else:
            filters |= Q(pk=token)

        school = School.objects.filter(filters).first()
        if school is None:
            raise CommandError(f"School not found: {token!r}")
        return school
