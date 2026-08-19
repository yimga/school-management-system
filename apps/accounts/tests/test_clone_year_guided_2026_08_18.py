"""Clone-year guided path: create the target year before copying structure."""

from __future__ import annotations

from datetime import date

from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.academics.models import AcademicYear
from apps.accounts.models import User
from apps.accounts.views_rollover import clone_year_setup
from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"])
class CloneYearGuidedPathTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Clone Guide High",
            slug="clone-guide",
            subdomain="clone-guide",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="adm_clone_guide",
            password="x",
            is_staff=True,
            is_superuser=True,
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.factory = RequestFactory()

    def _call(self, method="get", **post):
        request = getattr(self.factory, method)("/workflow/clone-year/", data=post or None)
        request.user = self.user
        request.school = self.school
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        MessageMiddleware(lambda r: None).process_request(request)
        return clone_year_setup(request)

    def test_no_years_shows_create_year_cta_not_clone_form(self):
        response = self._call("get")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Create that new year first", html)
        self.assertNotIn('id="source_year"', html)

    def test_post_refused_until_two_years_exist(self):
        AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        response = self._call("post", source_year="1", target_year="2")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Create that new year first", html)

    def test_two_years_renders_clone_form(self):
        AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        AcademicYear.objects.create(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_active=False,
        )
        response = self._call("get")
        html = response.content.decode("utf-8")
        self.assertIn('id="source_year"', html)
        self.assertIn("2026/2027", html)
