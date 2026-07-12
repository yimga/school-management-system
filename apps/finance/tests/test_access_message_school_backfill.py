"""Finance access-grant notification Messages must carry the tenant school.

``request_finance_access`` builds ``communication.Message`` rows and ``bulk_create``s
them — which bypasses ``Message.save()``'s school backfill. Without an explicit
``school=`` the rows land ``school=NULL``, dropping out of school-scoped consumers
(e.g. one-record/export) and surviving a school-scoped GDPR purge as orphan PII
(same class as the Attendance.school NULL fix).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.communication.models import Message
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentGuardian, StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School


def _enable_access_requests():
    site = get_platform_site_settings_record(create=True)
    flags = {
        **dict(site.get_backend_feature_flags()),
        "allow_finance_access_requests": True,
        "require_guardian_finance_opt_in": True,
    }
    site.apply_feature_control_state(backend_feature_flags=flags, field_updates={})


class AccessRequestMessageSchoolTests(TestCase):
    def setUp(self):
        _enable_access_requests()
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Fin {uid}", slug=f"fin-{uid}", subdomain=f"fin-{uid}"
        )
        self.year = AcademicYear.objects.create(
            name=f"2025/2026-{uid}",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            school=self.school,
        )
        self.dept = Department.objects.create(school=self.school, name="Gen", code=f"G-{uid}")
        self.spec = Specialty.objects.create(
            school=self.school, department=self.dept, name="Gen", code=f"GS-{uid}"
        )
        self.classroom = Classroom.objects.create(
            school=self.school, academic_year=self.year, department=self.dept,
            name="Form 1", code=f"F1-{uid}",
        )
        self.profile = ComplianceProfile.objects.create(name=f"CP {uid}", country_code="CM")
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Jae", last_name="Learner",
            student_code=f"STD-{uid}", admission_number=f"ADM-{uid}",
            academic_year=self.year, classroom=self.classroom, specialty=self.spec,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile, academic_year=self.year, student=self.student,
            total_amount=Decimal("100.00"), balance_amount=Decimal("100.00"),
        )
        self.parent = User.objects.create_user(username=f"par_{uid}", password="pw")
        self.parent.role = User.Role.PARENT
        self.parent.save(update_fields=["role"])
        self.admin = User.objects.create_user(
            username=f"adm_{uid}", password="pw", role=User.Role.ADMIN
        )
        StudentGuardian.objects.create(
            guardian_user=self.parent, student=self.student, can_view_finance=False
        )

    def test_request_access_messages_carry_school(self):
        from apps.finance.views_access import request_finance_access

        req = RequestFactory().post(
            reverse("finance:invoice_request_access", args=[self.invoice.id])
        )
        req.user = self.parent
        req.school = self.school
        req.session = {}
        setattr(req, "_messages", FallbackStorage(req))

        resp = request_finance_access(req, self.invoice.id)
        self.assertEqual(resp.status_code, 302)

        msgs = Message.objects.filter(sender=self.parent)
        self.assertTrue(msgs.exists(), "expected at least one admin notification message")
        # Every notification message is scoped to the tenant — none orphaned NULL.
        self.assertFalse(msgs.filter(school__isnull=True).exists())
        for m in msgs:
            self.assertEqual(m.school_id, self.school.id)
