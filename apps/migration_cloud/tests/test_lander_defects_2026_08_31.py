"""Two lander defects found 2026-08-31, locked so neither can come back.

DEFECT 1 -- ``guardian_lander`` called ``student_name_from_row(row)`` without
importing it. Python only evaluates that call when ``student_external_id`` is
falsy, i.e. on exactly the NAME-KEYED guardian files the name-resolution work
exists to support. The call sits OUTSIDE the per-row ``try``, so it did not
quarantine the row: the ``NameError`` escaped ``land()`` and aborted the whole
artifact, landing ZERO rows -- including the id-keyed rows that came after it.
Eleven sibling landers import the helper at module level for the identical
guard; guardian_lander was the one that forgot.

DEFECT 2 -- ``sections_lander`` read the department name from the row for
``name=`` but minted the department CODE from the hardcoded literal "General".
A "Science" department was created with a GENERAL-derived code. Worse:
``mint_scoped_code``'s hash fallback is deterministic in the name it is given,
so with a constant name the fallback is a per-school CONSTANT -- the 1st
distinct department took ``DPT<sid>-GENERAL``, the 2nd took the single fallback,
and the 3rd distinct department name in a school collided on the
``uniq_department_school_code`` constraint and quarantined its section row.

Both tests drive the REAL lander over real rows; neither asserts on internals.
"""

from __future__ import annotations

import symtable
from datetime import date
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.guardian_lander import GuardianLander
from apps.migration_cloud.landers.sections_lander import SectionsLander
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School

User = get_user_model()


class _LanderCtxMixin:
    def _ctx(self, school, dry_run=False) -> LanderContext:
        return LanderContext(
            school=school,
            schema_name="",
            bundle_id=None,
            artifact_id=None,
            dry_run=dry_run,
        )


class GuardianLanderNameKeyedArtifactTests(_LanderCtxMixin, TestCase):
    """A name-keyed guardian file must LAND, not abort the artifact."""

    def setUp(self):
        self.school = School.objects.create(
            name="Guardian Defect H",
            slug="guardian-defect-h",
            subdomain="guardian-defect-h",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Placed",
            admission_number="ADM-H-1",
        )

    def test_name_keyed_guardian_row_lands_instead_of_aborting_the_artifact(self):
        """No student_external_id -- the guard evaluates student_name_from_row."""
        result = GuardianLander().land(
            canonical_rows=iter(
                [
                    {
                        "student_name": "Ada Placed",
                        "first_name": "Ama",
                        "last_name": "Mensah",
                        "email": "ama.mensah@example.com",
                        "relationship": "MOTHER",
                    }
                ]
            ),
            ctx=self._ctx(self.school),
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, 1)
        link = StudentGuardian.objects.get(student=self.student)
        self.assertEqual(link.guardian_user.email, "ama.mensah@example.com")

    def test_one_name_keyed_row_does_not_abort_the_rest_of_the_artifact(self):
        """The blast radius that made this a P0: ONE name-keyed row used to take
        every id-keyed row in the same file down with it."""
        rows = [
            {
                "student_name": "Ada Placed",
                "first_name": "Ama",
                "last_name": "Mensah",
                "email": "ama.first@example.com",
            },
            {
                "student_external_id": "ADM-H-1",
                "first_name": "Kofi",
                "last_name": "Mensah",
                "email": "kofi.second@example.com",
            },
            {
                "student_external_id": "ADM-H-1",
                "first_name": "Yaa",
                "last_name": "Mensah",
                "email": "yaa.third@example.com",
            },
        ]
        result = GuardianLander().land(
            canonical_rows=iter(rows), ctx=self._ctx(self.school)
        )
        # Every row is accounted for -- the artifact ran to completion.
        self.assertEqual(
            result.created + result.updated + result.skipped + result.quarantined,
            len(rows),
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(
            StudentGuardian.objects.filter(student=self.student).count(), len(rows)
        )

    def test_name_keyed_row_without_guardian_identity_is_a_row_level_refusal(self):
        """Still no student_external_id, so the same call is still evaluated --
        but this row is genuinely unusable. It must be HELD, not fatal."""
        result = GuardianLander().land(
            canonical_rows=iter(
                [{"student_name": "Ada Placed", "relationship": "MOTHER"}]
            ),
            ctx=self._ctx(self.school),
        )
        self.assertEqual(result.quarantined, 1)
        self.assertIn("Missing student_external_id or identity", result.errors[0])
        self.assertFalse(StudentGuardian.objects.exists())


class SectionsLanderDepartmentCodeTests(_LanderCtxMixin, TestCase):
    """A provisioned department's code must be minted from ITS OWN name."""

    def setUp(self):
        self.school = School.objects.create(
            name="Sections Defect H",
            slug="sections-defect-h",
            subdomain="sections-defect-h",
        )
        AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )

    def test_department_code_is_minted_from_the_row_department_not_general(self):
        result = SectionsLander().land(
            canonical_rows=iter(
                [
                    {
                        "section_code": "SCI-7A",
                        "name": "Science Grade 7A",
                        "department": "Science",
                        "academic_year": "2025/2026",
                    }
                ]
            ),
            ctx=self._ctx(self.school),
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        dept = Department.objects.get(school=self.school, name="Science")
        self.assertIn("SCIENCE", dept.code.upper())
        self.assertNotIn("GENERAL", dept.code.upper())

    def test_three_distinct_departments_all_land_with_distinct_codes(self):
        """The constant-name mint gave a school exactly TWO usable department
        codes; the third distinct department broke uniq_department_school_code
        and its section row quarantined."""
        rows = [
            {
                "section_code": tag + "-7A",
                "name": dept + " Grade 7A",
                "department": dept,
                "academic_year": "2025/2026",
            }
            for tag, dept in (("SCI", "Science"), ("ART", "Arts"), ("MUS", "Music"))
        ]
        result = SectionsLander().land(
            canonical_rows=iter(rows), ctx=self._ctx(self.school)
        )
        self.assertEqual(result.errors, [])
        self.assertEqual(result.quarantined, 0)
        self.assertEqual(result.created, len(rows))
        self.assertEqual(
            Classroom.objects.filter(school=self.school).count(), len(rows)
        )

        depts = list(Department.objects.filter(school=self.school))
        self.assertEqual(sorted(d.name for d in depts), ["Arts", "Music", "Science"])
        codes = [d.code for d in depts]
        self.assertEqual(len(set(codes)), len(codes), "colliding codes: %r" % (codes,))
        for dept_row in depts:
            self.assertIn(
                dept_row.name.upper()[:4],
                dept_row.code.upper(),
                "%s minted from %s" % (dept_row.name, dept_row.code),
            )

    def test_an_existing_department_keeps_its_code(self):
        """The mint lives on get_or_create_named's CREATE path only -- a
        re-import must never re-code a department the tenant already has."""
        existing = Department.objects.create(
            school=self.school, name="Science", code="LEGACY-SCI"
        )
        result = SectionsLander().land(
            canonical_rows=iter(
                [
                    {
                        "section_code": "SCI-8B",
                        "name": "Science Grade 8B",
                        "department": "Science",
                        "academic_year": "2025/2026",
                    }
                ]
            ),
            ctx=self._ctx(self.school),
        )
        self.assertEqual(result.errors, [])
        existing.refresh_from_db()
        self.assertEqual(existing.code, "LEGACY-SCI")
        self.assertEqual(Department.objects.filter(school=self.school).count(), 1)


class LanderModuleGlobalsResolveTests(SimpleTestCase):
    """Static guard for the CLASS of bug defect 1 belongs to.

    The NameError was invisible for as long as no customer uploaded a name-keyed
    guardian file. Every name a lander module reads from its GLOBAL namespace
    must be bound at module level (imported or defined) or be a builtin -- a
    function-local import in a DIFFERENT function does not count, which is
    exactly how the guardian one hid.
    """

    def test_no_lander_references_an_unimported_module_global(self):
        import builtins

        import apps.migration_cloud.landers as landers_pkg

        pkg_dir = Path(landers_pkg.__file__).resolve().parent
        paths = sorted(pkg_dir.glob("*.py"))
        self.assertGreater(len(paths), 20, "lander package did not enumerate")

        builtin_names = set(dir(builtins))
        offenders: list[str] = []

        def walk(table, module_bound, scope, path):
            for sym in table.get_symbols():
                name = sym.get_name()
                if not sym.is_referenced():
                    continue
                if (
                    sym.is_local()
                    or sym.is_parameter()
                    or sym.is_free()
                    or sym.is_imported()
                    or sym.is_assigned()
                ):
                    continue
                if name.startswith("__") and name.endswith("__"):
                    continue  # interpreter-injected (PEP 649 annotate scopes)
                if name in module_bound or name in builtin_names:
                    continue
                offenders.append(
                    "%s:%s: %s" % (path.name, scope or "<module>", name)
                )
            for child in table.get_children():
                walk(
                    child,
                    module_bound,
                    ("%s.%s" % (scope, child.get_name())) if scope else child.get_name(),
                    path,
                )

        for path in paths:
            source = path.read_bytes().decode("utf-8")
            top = symtable.symtable(source, str(path), "exec")
            module_bound = {
                s.get_name()
                for s in top.get_symbols()
                if s.is_assigned() or s.is_imported()
            }
            walk(top, module_bound, "", path)

        self.assertEqual(sorted(set(offenders)), [])

    def test_the_static_guard_actually_bites(self):
        """A detector's zero is worth nothing until it is shown to fire."""
        source = (
            "from ._helpers import record_row_error\n"
            "def land(row):\n"
            "    if not student_name_from_row(row):\n"
            "        record_row_error(row)\n"
        )
        top = symtable.symtable(source, "<planted>", "exec")
        module_bound = {
            s.get_name()
            for s in top.get_symbols()
            if s.is_assigned() or s.is_imported()
        }
        land = top.lookup("land").get_namespace()
        unresolved = {
            s.get_name()
            for s in land.get_symbols()
            if s.is_referenced()
            and not (s.is_local() or s.is_parameter() or s.is_free())
            and s.get_name() not in module_bound
        }
        self.assertIn("student_name_from_row", unresolved)
        self.assertNotIn("record_row_error", unresolved)
