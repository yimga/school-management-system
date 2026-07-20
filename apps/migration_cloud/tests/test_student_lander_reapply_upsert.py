"""Student lander must re-apply without UNIQUE(admission_number) quarantine."""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.student_lander import StudentLander
from apps.people.models import StudentProfile
from apps.schools.models import School


class StudentLanderReapplyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Lander Reapply School",
            slug="lander-reapply-school",
            subdomain="lander-reapply-school",
            is_active=True,
            country_code="CM",
        )

    def test_reapply_same_external_id_updates_not_quarantines(self):
        lander = StudentLander()
        ctx = LanderContext(
            school=self.school,
            bundle_id=1,
            artifact_id=1,
            dry_run=False,
            schema_name="",
        )
        rows = [
            {
                "external_id": "PS-TEST-001",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "admission_number": "ADM-001",
                "enrollment_status": "active",
            }
        ]
        first = lander.land(canonical_rows=iter(rows), ctx=ctx)
        self.assertEqual(first.created, 1, first.errors)
        self.assertEqual(first.quarantined, 0, first.errors)
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 1)

        second = lander.land(canonical_rows=iter(rows), ctx=ctx)
        self.assertEqual(second.quarantined, 0, second.errors)
        self.assertGreaterEqual(second.updated + second.skipped, 1, second.errors)
        self.assertEqual(StudentProfile.objects.filter(school=self.school).count(), 1)
        student = StudentProfile.objects.get(school=self.school)
        # Upsert key is student_code=external_id; admission_number from CSV kept.
        self.assertEqual(student.student_code, "PS-TEST-001")
        self.assertEqual(student.admission_number, "ADM-001")
