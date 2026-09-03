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
from django.db import transaction

from apps.academics.models import Department, Specialty, SpecialtySubject, Subject
from apps.people.models import StudentProfile, TeacherProfile


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
        subject_names = set(
            Subject.objects.filter(school=school).values_list("name", flat=True)
        )

        plan = {
            "subjects_promoted_from_departments": [],
            "phantom_specialties_removed": [],
            "phantom_departments_removed": [],
            "curriculum_links_created": 0,
        }

        # Use .values() so reads stay minimal on healed schemas.
        for dept in Department.objects.filter(school=school).values("id", "name"):
            name = dept["name"]
            if name in subject_names:
                plan["phantom_departments_removed"].append(name)
            elif Subject.objects.filter(school=school, name__iexact=name).exists():
                plan["subjects_promoted_from_departments"].append(name)

        for sp in Specialty.objects.filter(school=school).values("id", "name"):
            name = sp["name"]
            if name in subject_names:
                plan["phantom_specialties_removed"].append(name)
            elif Subject.objects.filter(school=school, name__iexact=name).exists():
                plan["phantom_specialties_removed"].append(name)

        self.stdout.write(f"School: {school.name} ({school.subdomain})")
        for key, val in plan.items():
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

        with transaction.atomic():
            removed_specs = self._remove_phantom_specialties(school, subject_names)
            removed_depts = self._remove_phantom_departments(school, subject_names)
            links = self._ensure_curriculum_links(school)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Applied: removed {removed_specs} phantom specialties, "
                    f"{removed_depts} phantom departments, "
                    f"created/verified {links} curriculum links."
                )
            )

    @staticmethod
    def _resolve_school(token: str):
        import uuid

        from apps.schools.models import School
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

    @staticmethod
    def _remove_phantom_specialties(school, subject_names: set[str]) -> int:
        removed = 0
        for sp in Specialty.objects.filter(school=school).values("id", "name"):
            sp_id = sp["id"]
            name = sp["name"]
            if name not in subject_names and not Subject.objects.filter(
                school=school, name__iexact=name
            ).exists():
                continue
            if StudentProfile.objects.filter(school=school, specialty_id=sp_id).exists():
                continue
            SpecialtySubject.objects.filter(specialty_id=sp_id).delete()
            Specialty.objects.filter(pk=sp_id).delete()
            removed += 1
        return removed

    @staticmethod
    def _remove_phantom_departments(school, subject_names: set[str]) -> int:
        removed = 0
        for dept in Department.objects.filter(school=school).values("id", "name"):
            dept_id = dept["id"]
            name = dept["name"]
            if name not in subject_names:
                continue
            if name.lower() == "general":
                continue
            if TeacherProfile.objects.filter(school=school, department_id=dept_id).exists():
                continue
            if Specialty.objects.filter(school=school, department_id=dept_id).exists():
                continue
            if StudentProfile.objects.filter(
                school=school, specialty__department_id=dept_id
            ).exists():
                continue
            Department.objects.filter(pk=dept_id).delete()
            removed += 1
        return removed

    @staticmethod
    def _ensure_curriculum_links(school) -> int:
        from apps.academics.structure_provisioning import ensure_specialty_curriculum

        summary = ensure_specialty_curriculum(school)
        return int(summary.get("created_links") or 0)
