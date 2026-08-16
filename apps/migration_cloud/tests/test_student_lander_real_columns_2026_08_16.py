"""Student lander must land real SIS columns into real StudentProfile columns.

The operator reported "Place of Birth" / "Joining Date" / "Mobile Number"
landing at 0% custom_field on the live tenant. StudentProfile HAS first-class
columns for the first two (place_of_birth / joined_date) and a parent_phone
column for the third, so the importer must write them into their real home —
and sweep anything with no canonical home into the student's own
``custom_attributes`` so nothing on the roster is ever dropped.
"""

from __future__ import annotations

import datetime

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.people.models import StudentProfile
from apps.schools.models import School


class StudentLanderRealColumnsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Real Columns School",
            slug="real-columns-school",
            subdomain="real-columns-school",
            is_active=True,
            country_code="CM",
        )
        self.lander = StudentLander()
        self.ctx = LanderContext(
            school=self.school,
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
            schema_name="",
        )

    def _land(self, row):
        return self.lander.land(canonical_rows=iter([row]), ctx=self.ctx)

    def test_real_columns_land_into_real_fields(self):
        res = self._land({
            "external_id": "PS-RC-001",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "place_of_birth": "Buea",
            "joined_date": "2025-09-04",
            "joined_term": "Term 1",
            "section": "Blue",
            "exam_candidate_number": "1234567",
            "exam_center_code": "0505",
        })
        self.assertEqual(res.created, 1, res.errors)
        self.assertEqual(res.quarantined, 0, res.errors)
        s = StudentProfile.objects.get(school=self.school, student_code="PS-RC-001")
        self.assertEqual(s.place_of_birth, "Buea")
        self.assertEqual(s.joined_date, datetime.date(2025, 9, 4))
        self.assertEqual(s.joined_term, "Term 1")
        self.assertEqual(s.section, "Blue")
        self.assertEqual(s.exam_candidate_number, "1234567")
        self.assertEqual(s.exam_center_code, "0505")

    def test_phone_falls_back_to_parent_phone_when_no_student_phone(self):
        # StudentProfile has no student `phone` column but does have parent_phone,
        # so a lone roster "Mobile Number" lands in the real column, not a DFV.
        self.assertNotIn("phone", {f.name for f in StudentProfile._meta.get_fields()})
        self._land({
            "external_id": "PS-RC-002",
            "first_name": "Grace",
            "last_name": "Hopper",
            "phone": "+237677000000",
        })
        s = StudentProfile.objects.get(school=self.school, student_code="PS-RC-002")
        self.assertEqual(s.parent_phone, "+237677000000")

    def test_explicit_parent_phone_is_not_clobbered_by_phone_fallback(self):
        self._land({
            "external_id": "PS-RC-003",
            "first_name": "Alan",
            "last_name": "Turing",
            "parent_phone": "+237600000001",
            "phone": "+237699999999",
        })
        s = StudentProfile.objects.get(school=self.school, student_code="PS-RC-003")
        self.assertEqual(s.parent_phone, "+237600000001")

    def test_unmapped_columns_sweep_into_custom_attributes(self):
        # No canonical home → must still be ingested AND joined to the student.
        self._land({
            "external_id": "PS-RC-004",
            "first_name": "Katherine",
            "last_name": "Johnson",
            "custom_fields.nickname": "Kat",
            "_unmapped.house": "Red House",
            "custom_fields.blank_col": "",  # empty → skipped
        })
        s = StudentProfile.objects.get(school=self.school, student_code="PS-RC-004")
        self.assertEqual(s.custom_attributes.get("nickname"), "Kat")
        self.assertEqual(s.custom_attributes.get("house"), "Red House")
        self.assertNotIn("blank_col", s.custom_attributes)
