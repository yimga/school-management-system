"""portal_base header brand honors nav portal role (admin + parent session hat)."""

from __future__ import annotations

import re
import uuid
from datetime import date

from django.test import Client, TestCase
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.portal_roles import ACTIVE_PORTAL_ROLE_KEY
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School, SchoolMembership


class PortalBaseNavRoleHeaderTests(TestCase):
    """Integration: rendered parent dashboard shell links header brand to family home."""

    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name=f"Header Nav School {uid}",
            slug=f"hdr-nav-{uid}",
            subdomain=f"hdrnav{uid}",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            name="2026",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            school=cls.school,
        )
        dept = Department.objects.create(
            name="General",
            code=f"GN{uid[:4]}",
            school=cls.school,
        )
        sp = Specialty.objects.create(
            name="General",
            code=f"G{uid[:3]}",
            department=dept,
            school=cls.school,
        )
        cls.classroom = Classroom.objects.create(
            name="1A",
            code=f"1A-{uid}",
            academic_year=cls.year,
            department=dept,
            school=cls.school,
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Kid",
            last_name="Test",
            student_code=f"KID-{uid}",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=sp,
            date_of_birth=date(2014, 6, 1),
            is_active=True,
        )
        cls.admin_parent = User.objects.create_user(
            username=f"admin_parent_hat_{uid}",
            email=f"admin_parent_hat_{uid}@example.com",
            password="Test1234!long",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=cls.admin_parent,
            school=cls.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        StudentGuardian.objects.create(
            guardian_user=cls.admin_parent,
            student=cls.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            can_view_finance=True,
        )
        TOTPDevice.objects.create(
            user=cls.admin_parent,
            name="test-device",
            confirmed=True,
        )

    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.client.force_login(self.admin_parent)
        session = self.client.session
        session[ACTIVE_PORTAL_ROLE_KEY] = User.Role.PARENT
        session["school_id"] = str(self.school.pk)
        session["mfa_verified"] = True
        session.save()

        self.parent_home_path = reverse("portal:parent_dashboard")
        self.backend_path = reverse("accounts:backend_dashboard")

    def test_admin_with_parent_hat_header_brand_links_family_home(self):
        response = self.client.get(
            self.parent_home_path,
            HTTP_HOST=f"{self.school.subdomain}.runmycampus.com",
        )
        self.assertEqual(response.status_code, 200, msg=getattr(response, "url", ""))

        body = response.content.decode("utf-8", errors="replace")

        brand_match = re.search(
            r'<a[^>]*class="[^"]*tp-brand[^"]*"[^>]*href="([^"]+)"',
            body,
        )
        if brand_match is None:
            brand_match = re.search(
                r'href="([^"]+)"[^>]*class="[^"]*tp-brand[^"]*"',
                body,
            )
        self.assertIsNotNone(
            brand_match,
            "Expected v3 tp-brand header link on parent dashboard shell",
        )
        brand_href = brand_match.group(1)
        self.assertIn(
            self.parent_home_path.rstrip("/"),
            brand_href.rstrip("/"),
            msg=f"Header brand should point to family home, got {brand_href!r}",
        )
        self.assertNotIn(
            self.backend_path.rstrip("/"),
            brand_href.rstrip("/"),
            msg="Header brand must not send parent hat to staff backend",
        )
        self.assertIn("Family portal", body)
