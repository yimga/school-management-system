"""Batch 1149+ data platform finalization wiring — NL assistant surface + audit hooks."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.analytics.insight_registry import build_insights_for_school
from apps.analytics.views_governed import governed_intent_assistant
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.academics.models import AcademicYear

User = get_user_model()


class DataPlatformFinalizationTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Fin School",
            slug=f"fin-{uuid.uuid4().hex[:6]}",
            subdomain=f"fin-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="FY",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Fn",
            last_name="Student",
            student_code=f"FNS-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-F",
            academic_year=cls.year,
            date_of_birth=date(2011, 5, 5),
            is_active=True,
        )
        cls.profile = ComplianceProfile.objects.create(name="Fin profile", country_code="CM")
        Invoice.objects.create(
            school=cls.school,
            profile=cls.profile,
            academic_year=cls.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.OVERDUE,
            student=cls.student,
            total_amount=Decimal("90.00"),
            balance_amount=Decimal("90.00"),
            due_date=date(2025, 11, 1),
        )
        cls.perm_reports, _ = Permission.objects.get_or_create(
            code="reports.manage",
            defaults={"name": "Reports manage"},
        )

    def _staff(self):
        u = User.objects.create_user(username="dpf_" + uuid.uuid4().hex[:8], password="pw")
        u.feature_permissions.add(self.perm_reports)
        return u

    def test_nl_assistant_route_registered(self):
        url = reverse("analytics:governed_intent_assistant")
        self.assertIn("/analytics/governed/intent/", url)

    def test_insights_include_nl_nav_primary_action(self):
        user = self._staff()
        cards = build_insights_for_school(str(self.school.pk), user=user)
        nl_cards = [c for c in cards if c.get("id") == "governed_nl_assistant_nav"]
        self.assertTrue(nl_cards)
        pa = nl_cards[0].get("primary_action") or {}
        self.assertTrue(pa.get("path") or pa.get("primary_action_url"))

    def test_governed_intent_assistant_page_loads(self):
        user = self._staff()
        rf = RequestFactory()
        req = rf.get(reverse("analytics:governed_intent_assistant"))
        req.user = user
        req.school = self.school
        resp = governed_intent_assistant(req)
        self.assertEqual(resp.status_code, 200)
