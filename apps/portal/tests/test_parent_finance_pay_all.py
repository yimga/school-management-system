"""CEZGP batch 1515 — parent pay-all routes and wallet apply."""

from __future__ import annotations

import platform
import unittest
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings as django_settings
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import resolve, reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import Invoice, ParentWallet
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School, SchoolMembership


class ParentFinancePayAllRouteTests(SimpleTestCase):
    def test_pay_all_url_resolves(self):
        match = resolve("/portal/parent/finance/pay-all/")
        self.assertEqual(match.url_name, "parent_finance_pay_all")

    def test_reverse_parent_finance_pay_all(self):
        url = reverse("portal:parent_finance_pay_all")
        self.assertIn("pay-all", url)

    def test_family_billing_aggregator_importable(self):
        from apps.finance.family_billing_aggregator import (
            aggregate_family_balance,
            propose_payment_split,
        )

        self.assertTrue(callable(aggregate_family_balance))
        self.assertTrue(callable(propose_payment_split))


_TEMPLATES = Path(__file__).resolve().parents[3] / "templates" / "parent"

_LITE_MIDDLEWARE = tuple(
    m
    for m in django_settings.MIDDLEWARE
    if "compliance.middleware.AuditLoggingMiddleware" not in m
)

_SKIP_WINDOWS_SQLITE = unittest.skipIf(
    platform.system() == "Windows"
    and "sqlite3" in django_settings.DATABASES.get("default", {}).get("ENGINE", ""),
    "Skipped on Windows file-backed SQLite: nested audit writes lock the DB. "
    "ParentFinancePayAllContractTests cover the same contracts.",
)


class ParentFinancePayAllContractTests(SimpleTestCase):
    def test_finance_template_pay_all_hero(self):
        body = (_TEMPLATES / "finance.html").read_text(encoding="utf-8")
        self.assertIn("Pay all open balances", body)
        self.assertIn('data-rmc-pay-all-hero="1"', body)

    def test_confirm_template_regional_guidance(self):
        body = (_TEMPLATES / "finance_pay_all_confirm.html").read_text(encoding="utf-8")
        self.assertIn("Regional payment guidance", body)

    @patch("apps.portal.views_parent_finance.transaction.atomic")
    @patch("apps.portal.views_parent_finance.dispatch_payment_received_intent")
    @patch("apps.portal.views_parent_finance.pay_invoice_with_wallet")
    @patch("apps.portal.views_parent_finance.get_object_or_404")
    @patch("apps.portal.views_parent_finance.propose_payment_split")
    @patch("apps.portal.views_parent_finance.aggregate_family_balance")
    @patch("apps.portal.views_parent_finance._parent_finance_access_context")
    def test_wallet_post_applies_split(
        self,
        mock_access,
        mock_aggregate,
        mock_split,
        mock_get_invoice,
        mock_pay_wallet,
        mock_dispatch,
        mock_atomic,
    ):
        mock_atomic.return_value.__enter__.return_value = None
        mock_atomic.return_value.__exit__.return_value = None
        from apps.portal.views_parent_finance import parent_finance_pay_all

        mock_access.return_value = {
            "all_links": MagicMock(exists=MagicMock(return_value=True)),
            "finance_blocked": False,
        }
        summary = MagicMock()
        summary.has_open_balance = True
        summary.currency_mismatch = False
        summary.family_total_open_balance = Decimal("100.00")
        mock_aggregate.return_value = summary
        line = MagicMock(invoice_id=1, allocated_amount=Decimal("100.00"))
        split = MagicMock()
        split.blocked_reasons = []
        split.lines = [line]
        mock_split.return_value = split
        invoice = MagicMock(pk=1)
        mock_get_invoice.return_value = invoice
        mock_pay_wallet.return_value = (MagicMock(), MagicMock())
        mock_dispatch.return_value = {"dispatched": 1}

        school = MagicMock()
        wallet = MagicMock(balance=Decimal("200.00"))
        rf = RequestFactory()
        request = rf.post("/portal/parent/finance/pay-all/", {"payment_method": "wallet"})
        request.user = MagicMock(
            pk=42,
            is_authenticated=True,
            role=User.Role.PARENT,
        )
        request.school = school
        request.session = {}
        request._messages = FallbackStorage(request)
        with patch(
            "apps.portal.views_parent_finance.ParentWallet.objects.filter",
            return_value=MagicMock(first=MagicMock(return_value=wallet)),
        ):
            resp = parent_finance_pay_all(request)
        self.assertEqual(resp.status_code, 302)
        mock_pay_wallet.assert_called_once()
        mock_dispatch.assert_called_once()


@_SKIP_WINDOWS_SQLITE
@override_settings(MIDDLEWARE=_LITE_MIDDLEWARE)
class ParentFinancePayAllHttpTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="PayAll School",
            slug="payall-school",
            subdomain="payall-school",
            is_active=True,
            country_code="CM",
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school,
            name="Core",
            code=f"PA-{uuid.uuid4().hex[:6]}",
        )
        sp = Specialty.objects.create(department=dept, name="General", code="GN")
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 1",
            code="F1",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Pay",
            last_name="Kid",
            student_code=f"PA-KID-{uuid.uuid4().hex[:8]}",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=sp,
            date_of_birth=date(2012, 3, 1),
            is_active=True,
        )
        cls.parent = User.objects.create_user(
            username="payall_parent",
            password="testpass12",
        )
        cls.parent.role = User.Role.PARENT
        cls.parent.save(update_fields=["role"])
        SchoolMembership.objects.create(
            user=cls.parent,
            school=cls.school,
            role=User.Role.PARENT,
            is_primary=True,
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent,
            student=cls.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            can_view_finance=True,
        )
        cls.invoice = Invoice.objects.create(
            school=cls.school,
            student=cls.student,
            academic_year=cls.year,
            reference="INV-PAYALL-1",
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            status=Invoice.Status.ISSUED,
            issued_date=date(2026, 1, 1),
            due_date=date(2026, 2, 1),
        )
        ParentWallet.objects.create(
            school=cls.school,
            user=cls.parent,
            balance=Decimal("200.00"),
            currency_code="USD",
        )

    def setUp(self):
        self.client.force_login(self.parent)
        session = self.client.session
        session["school_id"] = str(self.school.pk)
        session.save()

    def test_finance_page_shows_pay_all_hero(self):
        resp = self.client.get(reverse("portal:parent_finance"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Pay all open balances", body)
        self.assertIn('data-rmc-pay-all-hero="1"', body)

    def test_pay_all_confirm_get(self):
        resp = self.client.get(reverse("portal:parent_finance_pay_all"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Regional payment guidance", body)

    @patch("apps.portal.views_parent_finance.dispatch_payment_received_intent")
    def test_pay_all_wallet_post_clears_invoice(self, mock_dispatch):
        mock_dispatch.return_value = {"dispatched": 1}
        resp = self.client.post(
            reverse("portal:parent_finance_pay_all"),
            {"payment_method": "wallet"},
        )
        self.assertEqual(resp.status_code, 302)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_amount, Decimal("0.00"))
        self.assertTrue(mock_dispatch.called)
