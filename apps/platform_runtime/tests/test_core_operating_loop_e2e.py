"""GEOS-99 batch 1389: core operating loop smoke (tenant + student + finance module)."""

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import Invoice
from apps.people.models import StudentProfile
from apps.schools.models import School


class CoreOperatingLoopE2ETests(TestCase):
    """Smoke: core entities import and school-scoped student row (full loop = Lane 2 pilot)."""

    def test_core_loop_school_student_and_invoice_model_wired(self):
        school = School.objects.create(
            name="Loop School",
            slug="loop-school",
            subdomain="loop-school",
            is_active=True,
        )
        user = User.objects.create_user(
            username="loop_student",
            password="Test1234!",
            role=User.Role.STUDENT,
        )
        profile = StudentProfile.objects.create(
            user=user,
            school=school,
            student_id="LOOP-001",
            first_name="Loop",
            last_name="Student",
        )
        self.assertEqual(profile.school_id, school.pk)
        self.assertTrue(Invoice._meta.get_field("school"))
