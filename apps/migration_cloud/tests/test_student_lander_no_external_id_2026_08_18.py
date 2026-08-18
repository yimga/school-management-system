"""A roster with no source-system id column must still import — idempotently.

Reported from a live tenant: 200/200 student rows quarantined
``missing_required``, 0 created, and because the bundle applies atomically the
valid subjects (108) and specialties (8) beside them were rolled back too. The
apply reported ``succeeded`` each time, five repairs in a row.

The rows were fine. The export was a plain roster --
``full_name / gender / date_of_birth / place_of_birth / grade_level / specialty``
-- with no id column, and the lander's gate is
``if not external_id or not first_name or not last_name``. That is an AND: a
combined-name split already existed and worked, but no ``external_id`` meant
quarantine regardless. A paper-to-digital school has no SIS id to give.

The fix must not simply drop the requirement. ``external_id`` is the upsert key
-- the reason re-running a bundle updates instead of duplicating -- so it is
DERIVED deterministically from the row's stable identity. These tests pin both
halves: the roster lands, AND re-applying it (a repair, or the second bundle
carrying the same files) updates rather than duplicating, including when the
student has been promoted to a new class between exports.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.people.models import StudentProfile
from apps.schools.models import School

# Shaped exactly like the quarantined production rows.
_ROSTER_ROW = {
    "full_name": "ANDONGMAD  FAVOUR ANGU",
    "gender": "Male",
    "date_of_birth": "2012-01-25",
    "place_of_birth": "EKONA - FAKO",
    "grade_level": "Form Four",
}


class StudentLanderNoExternalIdTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="No ExtId School",
            slug="no-extid-school",
            subdomain="no-extid-school",
            is_active=True,
            country_code="CM",
        )
        self.lander = StudentLander()
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def _land(self, row):
        return self.lander.land(canonical_rows=iter([dict(row)]), ctx=self.ctx)

    def test_roster_without_id_column_lands(self):
        res = self._land(_ROSTER_ROW)
        self.assertEqual(
            res.quarantined,
            0,
            f"a valid roster row was rejected for having no id column: {res.errors}",
        )
        self.assertEqual(res.created, 1)
        student = StudentProfile.objects.get(school=self.school)
        self.assertEqual(student.first_name.casefold(), "andongmad")
        self.assertTrue(student.last_name)

    def test_reapply_updates_instead_of_duplicating(self):
        """Repair / a second bundle with the same file must not double the roster."""
        self._land(_ROSTER_ROW)
        res = self._land(_ROSTER_ROW)
        self.assertEqual(res.created, 0, "re-apply created a duplicate student")
        self.assertEqual(res.updated, 1)
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 1)

    def test_promotion_resolves_to_the_same_student(self):
        """grade_level is volatile, so it must not participate in the derived key."""
        self._land(_ROSTER_ROW)
        promoted = dict(_ROSTER_ROW, grade_level="Form Five")
        res = self._land(promoted)
        self.assertEqual(res.created, 0, "a promoted student was duplicated")
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 1)

    def test_two_different_students_do_not_collide(self):
        self._land(_ROSTER_ROW)
        self._land(dict(_ROSTER_ROW, full_name="AWA BERTRAND", date_of_birth="2011-03-16"))
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 2)

    def test_row_with_no_name_at_all_is_still_quarantined(self):
        """An unidentifiable row must be rejected, never given an invented identity."""
        res = self._land({"gender": "Male", "grade_level": "Form Four"})
        self.assertEqual(res.created, 0)
        self.assertEqual(res.quarantined, 1)
