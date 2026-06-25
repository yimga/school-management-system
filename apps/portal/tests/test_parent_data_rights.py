"""Parent portal GDPR data rights."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig

User = get_user_model()


@override_settings(ALLOWED_HOSTS=["*"])
class ParentDataRightsTests(TestCase):
    def setUp(self):
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            name="Parent Rights School",
            slug="parent-rights-school",
            subdomain="parent-rights-school",
            is_active=True,
            is_approved=True,
            default_region=self.region,
        )
        self.parent = User.objects.create_user(
            username="parent_rights",
            email="parent@rights.test",
            password="testpass123",
            role=User.Role.PARENT,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Kid",
            last_name="Rights",
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent,
            student=self.student,
        )
        self.client = Client()

    def test_parent_data_rights_page_loads(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            "/portal/parent/data-rights/",
            HTTP_HOST="parent-rights-school.localhost",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data rights")

    def test_api_status_json(self):
        self.client.force_login(self.parent)
        response = self.client.get(
            "/portal/parent/data-rights/status.json",
            HTTP_HOST="parent-rights-school.localhost",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body.get("ok"))
        self.assertGreaterEqual(body.get("child_count", 0), 1)
