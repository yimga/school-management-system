"""Every PERSON lander must import a roster that carries no source-system id.

Companion to test_student_lander_no_external_id: the same AND-gate
(``if not external_id or ...``) sat in the alumni and staff landers, so the same
class of upload -- a plain name roster off a printed list or a payroll sheet --
was rejected wholesale there too. Alumni additionally had no combined-name split
at all, despite being the records LEAST likely to carry separate given/family
columns.

Scope is deliberate. ``external_id`` means two different things across the
engine: on a PERSON lander it is that person's own identity (derive it), but on
an EVENT lander (attendance / grades / finance) it is
``row['student_external_id']`` -- a FOREIGN REFERENCE to a student. Deriving one
there would invent a reference that matches no one and silently attach records
to nothing, so those landers are intentionally left alone and must keep
rejecting rows with no student reference.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers.alumni_lander import AlumniLander
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.staff_lander import StaffLander
from apps.schools.models import School


class PersonLanderNoExternalIdTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Person Lander School",
            slug="person-lander-school",
            subdomain="person-lander-school",
            is_active=True,
            country_code="CM",
        )
        self.ctx = LanderContext(
            school=self.school, bundle_id=1, artifact_id=1, dry_run=False, schema_name=""
        )

    def _land(self, lander, row):
        return lander.land(canonical_rows=iter([dict(row)]), ctx=self.ctx)

    def test_alumni_full_name_roster_without_id_lands(self):
        res = self._land(
            AlumniLander(),
            {"full_name": "NGWA COLLINS ABANG", "graduation_year": "2018"},
        )
        self.assertEqual(
            res.quarantined, 0, f"alumni roster row rejected: {res.errors}"
        )

    def test_alumni_reapply_is_idempotent(self):
        row = {"full_name": "NGWA COLLINS ABANG", "graduation_year": "2018"}
        self._land(AlumniLander(), row)
        res = self._land(AlumniLander(), row)
        self.assertEqual(res.created, 0, "re-applying duplicated an alumnus")

    def test_staff_roster_without_employee_id_lands(self):
        res = self._land(
            StaffLander(),
            {"full_name": "MBUA REGINA NAMONDO", "role": "TEACHER"},
        )
        self.assertEqual(res.quarantined, 0, f"staff roster row rejected: {res.errors}")

    def test_staff_row_with_no_name_or_id_is_still_quarantined(self):
        res = self._land(StaffLander(), {"role": "TEACHER"})
        self.assertEqual(res.created, 0)
        self.assertEqual(res.quarantined, 1)
