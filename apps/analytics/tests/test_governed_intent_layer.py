"""Governed NL intent layer — allowlisted mappings only; rejects SQL fragments."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.models import Permission
from apps.analytics.governed_intent import (
    match_governed_intent,
    rebuild_definition_for_intent,
    text_contains_disallowed_sql_fragment,
)
from apps.analytics.views_governed import governed_intent_execute, governed_intent_preview
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.academics.models import AcademicYear

User = get_user_model()


class GovernedIntentLayerTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Intent School",
            slug=f"intent-{uuid.uuid4().hex[:6]}",
            subdomain=f"intent-{uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="IY",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="In",
            last_name="Student",
            student_code=f"INS-{uuid.uuid4().hex[:6]}",
            admission_number="ADM-I",
            academic_year=cls.year,
            date_of_birth="2010-01-01",
            is_active=True,
        )
        cls.profile = ComplianceProfile.objects.create(name="Intent profile", country_code="CM")
        Invoice.objects.create(
            school=cls.school,
            profile=cls.profile,
            academic_year=cls.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.PARTIAL,
            student=cls.student,
            total_amount=Decimal("80.00"),
            balance_amount=Decimal("40.00"),
            due_date="2026-01-15",
        )
        cls.perm_reports, _ = Permission.objects.get_or_create(
            code="reports.manage",
            defaults={"name": "Reports manage"},
        )

    def _staff(self):
        u = User.objects.create_user(username="gil_" + uuid.uuid4().hex[:8], password="pw")
        u.feature_permissions.add(self.perm_reports)
        return u

    def test_unpaid_invoice_intent_maps(self):
        m = match_governed_intent("Please show unpaid invoices by class")
        self.assertTrue(m.supported)
        self.assertEqual(m.intent_id, "unpaid_invoices_by_class")
        self.assertEqual(m.governed_definition["dataset_id"], "invoices")

    def test_not_supported_safe(self):
        m = match_governed_intent("launch rockets to mars revenue")
        self.assertFalse(m.supported)
        self.assertEqual(m.reason, "not_supported")

    def test_sql_fragment_rejected(self):
        self.assertTrue(text_contains_disallowed_sql_fragment("select * from invoices"))
        m = match_governed_intent("select * from invoices unpaid by class")
        self.assertFalse(m.supported)
        self.assertEqual(m.reason, "disallowed_fragment")

    def test_preview_http_supported(self):
        user = self._staff()
        rf = RequestFactory()
        req = rf.post(
            "/analytics/governed/intent/preview/",
            data=json.dumps({"text": "students at risk marks"}),
            content_type="application/json",
        )
        req.user = user
        resp = governed_intent_preview(req)
        self.assertEqual(resp.status_code, 200)
        body = json.loads(resp.content.decode())
        self.assertTrue(body.get("supported"))

    def test_execute_requires_confirm_and_returns_insight_primary_action(self):
        user = self._staff()
        rf = RequestFactory()
        req = rf.post(
            "/analytics/governed/intent/execute/",
            data=json.dumps({"intent_id": "payment_failures", "confirm": False}),
            content_type="application/json",
        )
        req.user = user
        req.school = self.school
        resp_bad = governed_intent_execute(req)
        self.assertEqual(resp_bad.status_code, 400)

        req2 = rf.post(
            "/analytics/governed/intent/execute/",
            data=json.dumps({"intent_id": "payment_failures", "confirm": True}),
            content_type="application/json",
        )
        req2.user = user
        req2.school = self.school
        resp_ok = governed_intent_execute(req2)
        self.assertEqual(resp_ok.status_code, 200)
        payload = json.loads(resp_ok.content.decode())
        ins = payload.get("insight") or {}
        self.assertIn("primary_action", ins)

    def test_rebuild_definition_no_sql_strings(self):
        d = rebuild_definition_for_intent("reports_generated")
        self.assertIsNotNone(d)
        serialized = json.dumps(d)
        self.assertNotIn("SELECT", serialized.upper())
