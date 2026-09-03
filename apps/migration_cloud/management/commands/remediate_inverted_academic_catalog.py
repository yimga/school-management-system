"""Remediate inverted academic catalog rows for a single tenant.

Fixes the Cameroon TVET class of failure where subject master lists (TITLE /
DESCRIPTION / CATEGORY / coef) were mis-routed to ``Department`` + ``Specialty``,
or where teacher directory SPECIALTY tokens minted spurious departments.

Usage::

    manage.py remediate_inverted_academic_catalog --school gilead-tech --dry-run
    manage.py remediate_inverted_academic_catalog --school gilead-tech --apply
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import Department, Specialty, SpecialtySubject, Subject
from apps.people.models import TeacherProfile, StudentProfile


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

        from apps.schools.models import School

        school = self._resolve_school(options["school"])
        subject_names = set(
            Subject.objects.filter(school=school).values_list("name", flat=True)
        )

        plan = {
            "subjects_promoted_from_departments": [],
            "phantom_specialties_removed": [],
            "phantom_departments_removed": [],
            "curriculum_links_created": 0,
        }

        # Departments whose names duplicate an existing Subject → subject-shaped debris.
        for dept in Department.objects.filter(school=school):
            if dept.name in subject_names:
                plan["phantom_departments_removed"].append(dept.name)
                if options["apply"]:
                    continue  # handled in _apply
            elif Subject.objects.filter(school=school, name__iexact=dept.name).exists():
                plan["subjects_promoted_from_departments"].append(dept.name)

        # Specialties that mirror subject titles (mis-routed subject catalog).
        for sp in Specialty.objects.filter(school=school).select_related("department"):
            if sp.name in subject_names:
                plan["phantom_specialties_removed"].append(sp.name)
            elif Subject.objects.filter(school=school, name__iexact=sp.name).exists():
                plan["phantom_specialties_removed"].append(sp.name)

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
        from apps.schools.models import School
        from django.db.models import Q

        qs = School.objects.filter(
            Q(pk=token) | Q(subdomain=token) | Q(slug=token)
        )
        school = qs.first()
        if school is None:
            raise CommandError(f"School not found: {token!r}")
        return school

    @staticmethod
    def _remove_phantom_specialties(school, subject_names: set[str]) -> int:
        removed = 0
        for sp in Specialty.objects.filter(school=school):
            if sp.name not in subject_names and not Subject.objects.filter(
                school=school, name__iexact=sp.name
            ).exists():
                continue
            if StudentProfile.objects.filter(school=school, specialty=sp).exists():
                continue
            SpecialtySubject.objects.filter(specialty=sp).delete()
            sp.delete()
            removed += 1
        return removed

    @staticmethod
    def _remove_phantom_departments(school, subject_names: set[str]) -> int:
        removed = 0
        for dept in Department.objects.filter(school=school):
            if dept.name not in subject_names:
                continue
            if dept.name.lower() == "general":
                continue
            if TeacherProfile.objects.filter(school=school, department=dept).exists():
                continue
            if Specialty.objects.filter(school=school, department=dept).exists():
                continue
            if StudentProfile.objects.filter(school=school, specialty__department=dept).exists():
                continue
            dept.delete()
            removed += 1
        return removed

    @staticmethod
    def _ensure_curriculum_links(school) -> int:
        from apps.academics.structure_provisioning import ensure_specialty_curriculum

        summary = ensure_specialty_curriculum(school)
        return int(summary.get("created_links") or 0)
