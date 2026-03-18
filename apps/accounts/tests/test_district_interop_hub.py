"""Tenant District & LMS interop hub."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.accounts.views_district_interop import district_lms_interop
from apps.schools.models import School


class DistrictInteropHubTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Interop School",
            slug="interop-sch",
            subdomain="interop-sch",
            is_active=True,
        )
        self.admin = User.objects.create_user(username="interop_adm", password="x")
        self.admin.role = User.Role.ADMIN
        self.admin.save(update_fields=["role"])
        self.teacher = User.objects.create_user(username="interop_t", password="x")
        self.teacher.role = User.Role.TEACHER
        self.teacher.save(update_fields=["role"])

    def test_teacher_forbidden(self):
        req = self.factory.get("/authentication/backend/district-lms-interop/")
        req.user = self.teacher
        req.school = self.school
        resp = district_lms_interop(req)
        self.assertEqual(resp.status_code, 403)

    def test_admin_renders(self):
        req = self.factory.get("/authentication/backend/district-lms-interop/")
        req.user = self.admin
        req.school = self.school
        resp = district_lms_interop(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"OneRoster", resp.content)

    def test_anonymous_forbidden(self):
        req = self.factory.get("/authentication/backend/district-lms-interop/")
        req.user = AnonymousUser()
        req.school = self.school
        resp = district_lms_interop(req)
        self.assertIn(resp.status_code, (302, 403))
