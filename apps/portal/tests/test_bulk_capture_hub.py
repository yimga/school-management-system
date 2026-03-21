"""Wave 6: teacher bulk capture hub."""

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.portal.views_bulk_capture import teacher_bulk_capture_hub
from apps.people.models import TeacherProfile
from apps.schools.models import School

UserModel = get_user_model()


class TeacherBulkCaptureHubTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="BC School",
            slug=f"bc-{uuid.uuid4().hex[:10]}",
            subdomain=f"bc-{uuid.uuid4().hex[:10]}",
        )
        self.teacher = UserModel.objects.create_user(
            username=f"t-{uuid.uuid4().hex[:8]}",
            email="t@t.test",
            password="x",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=self.teacher, school=self.school)
        self.factory = RequestFactory()

    def test_hub_renders(self):
        req = self.factory.get("/portal/teacher/bulk-capture/")
        req.user = self.teacher
        resp = teacher_bulk_capture_hub(req)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bulk capture")
        self.assertContains(resp, "Student roll call")
        self.assertContains(resp, "Seating chart")
        self.assertContains(resp, "My classes")
