"""North Star SLICE 13 — passport membership + transcript vault services & portal."""

from __future__ import annotations

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentProfile
from apps.people.passport_services import (
    create_transcript_vault_item,
    get_or_create_passport_for_student,
    link_student_to_passport,
    list_visible_vault_items,
    user_can_view_passport,
)
from apps.people.student_passport_models import StudentPassportMembership
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School, SchoolMembership

_ALLOWED_HOSTS = [
    "testserver",
    "127.0.0.1",
    "localhost",
    "pv1.runmycampus.com",
    "pv2.runmycampus.com",
]


@override_settings(ALLOWED_HOSTS=_ALLOWED_HOSTS)
class StudentPassportVaultTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Pv",
            slug=f"pvv-{uuid.uuid4().hex[:8]}",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code=f"P{uuid.uuid4().hex[:5].upper()}",
            name="Pvland",
            timezone="UTC",
            default_currency="USD",
        )
        cls.school_a = School.objects.create(
            name="School Alpha",
            slug="pv1",
            subdomain="pv1",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )
        cls.school_b = School.objects.create(
            name="School Beta",
            slug="pv2",
            subdomain="pv2",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )
        cls.dept = Department.objects.create(name="Sci", code="SC")
        cls.spec = Specialty.objects.create(department=cls.dept, name="G", code="G")

        def _student(school: School, code: str) -> StudentProfile:
            year = AcademicYear.objects.create(
                name=f"Y-{school.pk}",
                start_date="2025-09-01",
                end_date="2026-06-30",
                is_active=True,
                school=school,
            )
            room = Classroom.objects.create(
                academic_year=year,
                department=cls.dept,
                name="C1",
                code=f"C-{uuid.uuid4().hex[:6]}",
                school=school,
            )
            return StudentProfile.objects.create(
                first_name="Pat",
                last_name=code,
                student_code=f"{code}-{uuid.uuid4().hex[:8]}",
                admission_number=f"PV-{school.pk}-{uuid.uuid4().hex[:10]}",
                academic_year=year,
                classroom=room,
                specialty=cls.spec,
                school=school,
                is_active=True,
            )

        cls.student_a = _student(cls.school_a, "SA")
        cls.student_b = _student(cls.school_b, "SB")

    def _staff(self, username: str, school: School, *, teacher: bool = False):
        role = User.Role.TEACHER if teacher else User.Role.ADMIN
        u = User.objects.create_user(
            username=username,
            password="passwordxx",
            role=role,
            is_staff=True,
        )
        SchoolMembership.objects.get_or_create(user=u, school=school, defaults={"role": "ADMIN"})
        return u

    def test_passport_created_for_student(self):
        admin = self._staff(f"a_{uuid.uuid4().hex[:8]}", self.school_a)
        passport, created = get_or_create_passport_for_student(self.student_a, admin)
        self.assertTrue(created)
        passport2, created2 = get_or_create_passport_for_student(self.student_a, admin)
        self.assertFalse(created2)
        self.assertEqual(passport.pk, passport2.pk)

    def test_explicit_second_school_link_requires_service_call(self):
        admin = self._staff(f"b_{uuid.uuid4().hex[:8]}", self.school_a)
        passport, _ = get_or_create_passport_for_student(self.student_a, admin)
        link_student_to_passport(passport, self.student_b, admin)
        self.assertEqual(
            StudentPassportMembership.objects.filter(passport=passport).count(),
            2,
        )

    def test_unauthorized_user_cannot_view_passport(self):
        admin_a = self._staff(f"c_{uuid.uuid4().hex[:8]}", self.school_a)
        outsider = User.objects.create_user(
            username=f"out_{uuid.uuid4().hex[:8]}",
            password="passwordxx",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        passport, _ = get_or_create_passport_for_student(self.student_a, admin_a)
        self.assertFalse(user_can_view_passport(outsider, passport))

    def test_transcript_item_has_verification_hash_when_bytes_provided(self):
        admin = self._staff(f"d_{uuid.uuid4().hex[:8]}", self.school_a)
        item = create_transcript_vault_item(
            self.student_a,
            artifact_type="TRANSCRIPT_PDF",
            artifact_bytes=b"hello-world",
            user=admin,
        )
        self.assertEqual(len(item.verification_hash), 64)

    def test_passport_detail_and_vault_routes_render(self):
        admin = self._staff(f"e_{uuid.uuid4().hex[:8]}", self.school_a)
        c = Client(HTTP_HOST="pv1.runmycampus.com")
        c.force_login(admin)
        url_p = reverse(
            "portal:student_passport_detail",
            urlconf="config.tenant_urls",
            kwargs={"student_profile_id": self.student_a.pk},
        )
        url_v = reverse(
            "portal:student_transcript_vault",
            urlconf="config.tenant_urls",
            kwargs={"student_profile_id": self.student_a.pk},
        )
        rp = c.get(url_p)
        rv = c.get(url_v)
        self.assertEqual(rp.status_code, 200)
        self.assertEqual(rv.status_code, 200)
        bp = rp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-student-passport="1"', bp)
        bv = rv.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-transcript-vault="1"', bv)

    def test_parent_blocked_from_passport_pages(self):
        u = User.objects.create_user(
            username=f"f_{uuid.uuid4().hex[:8]}",
            password="passwordxx",
            role=User.Role.PARENT,
        )
        SchoolMembership.objects.get_or_create(
            user=u, school=self.school_a, defaults={"role": "PARENT"}
        )
        c = Client(HTTP_HOST="pv1.runmycampus.com")
        c.force_login(u)
        url_p = reverse(
            "portal:student_passport_detail",
            urlconf="config.tenant_urls",
            kwargs={"student_profile_id": self.student_a.pk},
        )
        self.assertEqual(c.get(url_p).status_code, 403)

    def test_revoked_membership_hides_vault_items_for_school(self):
        admin = self._staff(f"g_{uuid.uuid4().hex[:8]}", self.school_a)
        passport, _ = get_or_create_passport_for_student(self.student_a, admin)
        create_transcript_vault_item(
            self.student_a,
            artifact_type="X",
            artifact_bytes=b"a",
            user=admin,
        )
        mem = StudentPassportMembership.objects.get(
            passport=passport,
            school=self.school_a,
            student_profile=self.student_a,
        )
        mem.consent_status = StudentPassportMembership.ConsentStatus.REVOKED
        mem.save(update_fields=["consent_status"])
        qs = list_visible_vault_items(admin, passport, school=self.school_a)
        self.assertEqual(qs.count(), 0)

    def test_student_profile_queryset_still_accessible(self):
        """Regression guard: StudentProfile remains primary enrollment surface."""
        self.assertTrue(
            StudentProfile.objects.filter(pk=self.student_a.pk).exists()
        )
