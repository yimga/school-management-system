"""M33 view wiring — the page must render and the actions must bind to ONE school.

The service tests next door prove the arithmetic. These prove the arithmetic is
reachable: that a real request renders it, that the buttons do what they say, and
-- the one that matters -- that the submit action cannot reach another school's
order even when the operator hands it that order's primary key.

Resolved against ``config.tenant_urls`` on purpose: the dev urlconf exposes a
wider URL surface than a real tenant gets, so a route that only works there is a
route that does not work.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.people.models import Enrollment, StudentProfile
from apps.schoolops.models import (
    PurchaseOrder,
    SupplyRequirement,
    Vendor,
    VendorProduct,
)
from apps.schoolops.views_procurement import ops_procurement
from apps.schools.models import School

User = get_user_model()


class ProcurementViewTests(TestCase):
    def setUp(self) -> None:
        set_urlconf("config.tenant_urls")
        self.factory = RequestFactory()
        self.school = self._school("proc-view")
        # is_staff short-circuits user_can_access_ops_extended_modules, which keeps
        # this test off the AccessRole seed data entirely.
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="adm@proc.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])

        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(
            school=self.school, name="Science", code="SCIV"
        )
        self.specialty = Specialty.objects.create(
            school=self.school, department=self.dept, name="General", code="GEN-PV"
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Form 4B",
            code="F4BV",
        )
        self.subject = Subject.objects.create(
            school=self.school, name="Chemistry", category=Subject.Category.GENERAL
        )
        SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1,
        )
        self.vendor = Vendor.objects.create(
            school=self.school, name="LabCo", is_certified=True, currency="USD"
        )
        self.goggles = VendorProduct.objects.create(
            school=self.school,
            vendor=self.vendor,
            sku="GOG-V1",
            name="Safety goggles",
            unit_price=Decimal("5.00"),
        )
        SupplyRequirement.objects.create(
            school=self.school,
            subject=self.subject,
            product=self.goggles,
            quantity_per_student=Decimal("1.00"),
        )
        self._enrol(3)

    def tearDown(self) -> None:
        set_urlconf(None)

    def _school(self, prefix):
        suffix = uuid.uuid4().hex[:10]
        return School.objects.create(
            name=f"{prefix} school",
            slug=f"{prefix}-{suffix}",
            subdomain=f"{prefix}-{suffix}",
            is_active=True,
            # Phase E waiver: grants the inventory module require_feature() demands.
            billing_type="COMPLIMENTARY",
        )

    def _enrol(self, count):
        for i in range(count):
            student = StudentProfile.objects.create(
                school=self.school,
                first_name=f"V{i}",
                last_name="Test",
                student_code=f"PROCV-{i}",
                academic_year=self.year,
                classroom=self.classroom,
                specialty=self.specialty,
                is_active=True,
            )
            Enrollment.objects.create(
                school=self.school,
                student=student,
                academic_year=self.year,
                classroom=self.classroom,
                entry_date=self.year.start_date,
            )

    def _req(self, method, *, user, school=None, data=None):
        path = "/backend/ops/procurement/"
        if method == "GET":
            request = self.factory.get(path)
        else:
            request = self.factory.post(path, data or {})
        request.user = user
        request.school = school or self.school
        SessionMiddleware(lambda x: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        return request

    def test_get_renders_the_derived_requirement(self):
        """The page must show what the timetable implies, not an empty shell."""
        response = ops_procurement(self._req("GET", user=self.admin))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Safety goggles", body)
        # 3 enrolled students x 1 per student.
        self.assertIn("Procurement", body)

    def test_generate_button_creates_a_draft_order(self):
        response = ops_procurement(
            self._req("POST", user=self.admin, data={"intent": "generate"})
        )

        self.assertEqual(response.status_code, 302)
        order = PurchaseOrder.objects.get(school=self.school)
        self.assertEqual(order.status, PurchaseOrder.Status.DRAFT)
        self.assertEqual(order.lines.get().quantity, 3)

    def test_submit_button_commits_the_draft(self):
        ops_procurement(self._req("POST", user=self.admin, data={"intent": "generate"}))
        order = PurchaseOrder.objects.get(school=self.school)

        response = ops_procurement(
            self._req(
                "POST",
                user=self.admin,
                data={"intent": "submit", "order_id": str(order.pk)},
            )
        )

        self.assertEqual(response.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.status, PurchaseOrder.Status.SUBMITTED)

    def test_submit_cannot_reach_another_schools_order(self):
        """Handing the view another tenant's primary key must change nothing.

        This is the test that would catch a filter(pk=...) that forgot school=.
        """
        other = self._school("proc-other")
        other_vendor = Vendor.objects.create(
            school=other, name="OtherCo", currency="USD"
        )
        foreign_order = PurchaseOrder.objects.create(
            school=other,
            vendor=other_vendor,
            status=PurchaseOrder.Status.DRAFT,
            source=PurchaseOrder.Source.MANUAL,
            currency="USD",
        )

        response = ops_procurement(
            self._req(
                "POST",
                user=self.admin,
                data={"intent": "submit", "order_id": str(foreign_order.pk)},
            )
        )

        self.assertEqual(response.status_code, 302)
        foreign_order.refresh_from_db()
        self.assertEqual(foreign_order.status, PurchaseOrder.Status.DRAFT)

    def test_non_numeric_order_id_is_rejected_not_crashed(self):
        response = ops_procurement(
            self._req(
                "POST",
                user=self.admin,
                data={"intent": "submit", "order_id": "'; DROP TABLE--"},
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PurchaseOrder.objects.filter(school=self.school).exists())
