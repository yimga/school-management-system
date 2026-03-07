from django.test import TestCase

from apps.accounts.models import User
from apps.compliance.gdpr_services import export_student_data_portability, gdpr_scrub_student
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class GDPRServicesTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="TGD",
            defaults={
                "name": "Test GDPR Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name="GDPR School",
            slug="gdpr-school",
            subdomain="gdpr-school",
            is_active=True,
            default_region=self.region,
        )
        self.student_user = User.objects.create_user(
            username="gdpr_student_user",
            email="student.gdpr@example.com",
            password="pass",
            role=User.Role.STUDENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            first_name="Jane",
            last_name="Doe",
            student_code="GDPR-STU-001",
            parent_phone="123456789",
            custom_attributes={"allergy": "none"},
        )
        self.guardian_user = User.objects.create_user(
            username="gdpr_parent_user",
            email="parent.gdpr@example.com",
            password="pass",
            role=User.Role.PARENT,
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian_user,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            phone="777777",
            email="guardian@example.com",
            address="Main street",
        )

    def test_portability_export_returns_payload(self):
        payload = export_student_data_portability(self.school.id, self.student.id, format="json")
        self.assertIsNotNone(payload)
        self.assertEqual(payload["student_id"], self.student.id)
        self.assertEqual(payload["student"]["first_name"], "Jane")
        self.assertIn("guardians", payload)

    def test_gdpr_scrub_dry_run(self):
        result = gdpr_scrub_student(self.school.id, self.student.id, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertIn("would_anonymize", result)

    def test_gdpr_scrub_executes_anonymization(self):
        result = gdpr_scrub_student(self.school.id, self.student.id, dry_run=False, requested_by_user_id=self.student_user.id)
        self.assertTrue(result.get("ok"))

        self.student.refresh_from_db()
        self.student_user.refresh_from_db()

        self.assertEqual(self.student.first_name, "Deleted")
        self.assertFalse(self.student.is_active)
        self.assertTrue(self.student.deleted_at is not None)

        self.assertEqual(self.student_user.first_name, "Deleted")
        self.assertFalse(self.student_user.is_active)
        self.assertIn("@invalid.local", self.student_user.email)

        guardian = StudentGuardian.objects.get(student=self.student)
        self.assertEqual(guardian.email, "")
        self.assertEqual(guardian.phone, "")
