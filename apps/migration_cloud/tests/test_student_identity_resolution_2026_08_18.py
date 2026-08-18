"""A school with no ID column must still be able to import attendance and grades.

The roster fix landed students without a source-system id by deriving a stable
surrogate key. But every history file the same school uploads -- attendance,
grades, fees, health -- identifies its students the ONLY way that school has ever
identified them: by name. Twelve of the twenty-four canonical domains reference a
student, and not one of them offered a name field, so:

  * the mapper had nowhere to put the name column, leaving the canonical row with
    no student reference at all; and
  * ``resolve_student`` matched ``external_id`` exactly, so even a row carrying a
    name could not find the student the roster had just created.

The result was a school that fixes its roster, re-imports, and hits an identical
wall of "no student with external_id=''" on every dependent file. This pins the
whole chain: name column -> canonical row -> resolved student -> landed record.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.migration_cloud.ontology.catalog import CANONICAL_ONTOLOGY
from apps.people.models import StudentProfile
from apps.schools.models import School

STUDENT_REFERENCING_DOMAINS = [
    domain
    for domain, fields in CANONICAL_ONTOLOGY.items()
    if any(f.startswith("student_external") for f in fields)
]


class EventDomainsOfferANameTests(TestCase):
    """The mapper cannot map a name column to a field that does not exist."""

    def test_every_student_referencing_domain_accepts_a_name(self):
        missing = [
            domain
            for domain in STUDENT_REFERENCING_DOMAINS
            if "student_name" not in CANONICAL_ONTOLOGY[domain]
        ]
        self.assertEqual(
            missing,
            [],
            "these domains can only identify a student by an id the school does "
            f"not have: {missing}",
        )

    def test_the_name_field_carries_the_real_world_synonyms(self):
        synonyms = CANONICAL_ONTOLOGY["attendance"]["student_name"]["synonyms"]
        flat = {s.lower() for values in synonyms.values() for s in values}
        for expected in ("student_name", "name", "nom", "nom_de_l_eleve"):
            self.assertIn(expected, flat, f"{expected!r} is how real files spell it")


class ResolveStudentByNameTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Identity School",
            slug="identity-school",
            subdomain="identity-school",
            is_active=True,
        )
        self.ctx = LanderContext(
            school=self.school,
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
        )
        # The roster: no id column at all, exactly as uploaded.
        StudentLander().land(
            canonical_rows=iter(
                [
                    {"full_name": "ANDONGMAD FAVOUR ANGU", "date_of_birth": "2012-01-25"},
                    {"full_name": "AWA BERTRAND NDIVE", "date_of_birth": "2011-06-03"},
                ]
            ),
            ctx=self.ctx,
        )
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 2)

    def _resolve(self, **row):
        from apps.migration_cloud.landers._helpers import (
            resolve_student,
            student_lookup_field,
            model_field_names,
        )

        return resolve_student(
            ctx=self.ctx,
            student_model=StudentProfile,
            lookup_field=student_lookup_field(model_field_names(StudentProfile)),
            external_id=row.pop("external_id", ""),
            row=row,
        )

    def test_a_row_naming_the_student_resolves(self):
        student = self._resolve(student_name="ANDONGMAD FAVOUR ANGU")
        self.assertIsNotNone(
            student, "an attendance row naming the student found nobody"
        )
        # Which token became the surname is the SPLIT's business, not the
        # resolver's; what matters here is that the right person was found.
        self.assertEqual(str(student.date_of_birth), "2012-01-25")

    def test_resolution_tolerates_case_and_spacing_drift(self):
        self.assertIsNotNone(self._resolve(student_name="  awa   bertrand ndive "))

    def test_an_unknown_name_still_resolves_to_nobody(self):
        self.assertIsNone(
            self._resolve(student_name="NOT A REAL STUDENT"),
            "a name nobody carries must not resolve to an arbitrary student",
        )

    def test_an_external_id_still_wins_over_a_name(self):
        from apps.migration_cloud.landers._helpers import (
            model_field_names,
            student_lookup_field,
        )

        field = student_lookup_field(model_field_names(StudentProfile))
        target = StudentProfile.objects.filter(school=self.school).first()
        setattr(target, field, "PS-1029")
        target.save(update_fields=[field])
        resolved = self._resolve(
            external_id="PS-1029", student_name="AWA BERTRAND NDIVE"
        )
        self.assertEqual(
            resolved.pk, target.pk, "the explicit id must outrank the name"
        )

    def test_a_name_shared_by_two_students_is_not_guessed(self):
        """Ambiguity must be reported, never silently resolved to the first match."""
        StudentLander().land(
            canonical_rows=iter(
                [{"full_name": "ANDONGMAD FAVOUR ANGU", "date_of_birth": "2009-09-09"}]
            ),
            ctx=self.ctx,
        )
        self.assertEqual(
            StudentProfile.objects.filter(school=self.school).count(),
            3,
            "the two same-named students must be distinct people",
        )
        self.assertIsNone(
            self._resolve(student_name="ANDONGMAD FAVOUR ANGU"),
            "an ambiguous name resolved to one of the candidates by guessing",
        )

    def test_a_date_of_birth_disambiguates_a_shared_name(self):
        StudentLander().land(
            canonical_rows=iter(
                [{"full_name": "ANDONGMAD FAVOUR ANGU", "date_of_birth": "2009-09-09"}]
            ),
            ctx=self.ctx,
        )
        student = self._resolve(
            student_name="ANDONGMAD FAVOUR ANGU", student_date_of_birth="2009-09-09"
        )
        self.assertIsNotNone(student, "dob should have separated the two namesakes")
        self.assertEqual(str(student.date_of_birth), "2009-09-09")

    def test_another_schools_student_is_never_resolved(self):
        other = School.objects.create(
            name="Other", slug="other-school", subdomain="other-school", is_active=True
        )
        StudentLander().land(
            canonical_rows=iter([{"full_name": "SOLO CHILD", "date_of_birth": "2010-02-02"}]),
            ctx=LanderContext(
                school=other, schema_name="", bundle_id=2, artifact_id=2, dry_run=False
            ),
        )
        self.assertIsNone(
            self._resolve(student_name="SOLO CHILD"),
            "name resolution crossed a tenant boundary",
        )


class UnresolvedReasonTests(TestCase):
    """A quarantine reason must name the fix, not an internal column."""

    def setUp(self):
        self.school = School.objects.create(
            name="Reason School",
            slug="reason-school",
            subdomain="reason-school",
            is_active=True,
        )
        self.ctx = LanderContext(
            school=self.school,
            schema_name="",
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
        )
        StudentLander().land(
            canonical_rows=iter(
                [
                    {"full_name": "TWIN NAME", "date_of_birth": "2012-01-25"},
                    {"full_name": "TWIN NAME", "date_of_birth": "2013-02-02"},
                ]
            ),
            ctx=self.ctx,
        )

    def _reason(self, **kwargs):
        from apps.migration_cloud.landers._helpers import unresolved_student_reason

        return unresolved_student_reason(
            domain="attendance",
            ctx=self.ctx,
            student_model=StudentProfile,
            **kwargs,
        )

    def test_no_reason_leaks_an_internal_column_name(self):
        for reason in (
            self._reason(row={}, external_id=""),
            self._reason(row={"student_name": "GHOST PUPIL"}),
            self._reason(row={}, external_id="PS-9", lookup_field="admission_number"),
            self._reason(row={"student_name": "TWIN NAME"}),
        ):
            self.assertNotIn("admission_number", reason, reason)
            self.assertNotIn("external_id", reason, reason)

    def test_an_ambiguous_name_says_so_and_says_what_to_add(self):
        reason = self._reason(row={"student_name": "TWIN NAME"})
        self.assertIn("more than one", reason)
        self.assertIn("date of birth", reason)

    def test_an_unknown_name_suggests_importing_the_roster_first(self):
        reason = self._reason(row={"student_name": "GHOST PUPIL"})
        self.assertIn("GHOST PUPIL", reason)
        self.assertIn("student list", reason)

    def test_a_row_with_no_reference_at_all_says_which_column_to_add(self):
        reason = self._reason(row={}, external_id="")
        self.assertIn("does not say which pupil", reason)

    def test_an_id_only_miss_suggests_adding_a_name_column(self):
        reason = self._reason(row={}, external_id="PS-404")
        self.assertIn("PS-404", reason)
        self.assertIn("name column", reason)
