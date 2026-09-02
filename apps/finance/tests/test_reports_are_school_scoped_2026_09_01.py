"""Finance reporting is scoped by COUNTRY, not by school.

``Invoice.profile`` points at ComplianceProfile - a regulatory profile carrying
country_code, currency, min wage and leave days. Every school in a country shares
one. So ``Invoice.objects.filter(profile=profile)`` bounds a report to a country,
and the finance intelligence page aggregates arrears, AR, collection rate and
PAYROLL liabilities across every school in it.

On the schema-per-tenant cloud the schema hides that. On the shared-schema RLS
edge it does not, and the markers on those queries say
``scoped-via-surrounding-tenant-context`` - a reason that is true on one
deployment and false on the other.

``views_payment_readiness_dashboard`` in this same app already does it right: it
resolves request.school and 403s without one, and its docstring says the school
is what keeps the numbers scoped. These tests hold the reporting views to the
pattern their neighbour already follows.
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import patch
from decimal import Decimal

from django.contrib.sessions.backends.db import SessionStore
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile, Invoice
from apps.finance.views_reports import finance_reports
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass

OTHER_SCHOOL_AR = Decimal("987654.00")
MY_AR = Decimal("100.00")


def _school(slug):
    return School.objects.create(
        id=uuid.uuid4(), name=slug.title(), slug=slug, subdomain=slug,
        is_active=True, is_approved=True, country_code="CM", settings={},
    )


class FinanceReportsAreSchoolScopedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with rls_bypass():
            cls.profile = ComplianceProfile.objects.create(name="Cameroon", country_code="CM")
            cls.mine = _school("scoped-mine")
            cls.rival = _school("scoped-rival")
            # Same country profile, different schools. This is the collision:
            # nothing about `profile` distinguishes these two rows.
            cls.staff = User.objects.create_user(
                username="finscope", password="Pass_1234",
                email="finscope@example.com", is_staff=True, is_superuser=True,
            )
            cls.my_invoice = Invoice.objects.create(
                profile=cls.profile, school=cls.mine, total_amount=MY_AR,
                balance_amount=MY_AR, due_date=date(2020, 1, 1),
            )
            cls.rival_invoice = Invoice.objects.create(
                profile=cls.profile, school=cls.rival, total_amount=OTHER_SCHOOL_AR,
                balance_amount=OTHER_SCHOOL_AR, due_date=date(2020, 1, 1),
            )

    def _get(self, school):
        request = RequestFactory().get("/finance/reports/")
        request.user = self.staff
        request.school = school
        request.session = SessionStore()
        return finance_reports(request)

    def test_the_two_schools_really_do_share_one_compliance_profile(self):
        """Arm the trap: if these were separate profiles the test proves nothing."""
        self.assertEqual(self.my_invoice.profile_id, self.rival_invoice.profile_id)
        self.assertNotEqual(self.my_invoice.school_id, self.rival_invoice.school_id)
        both = Invoice.objects.filter(profile=self.profile).count()
        self.assertEqual(both, 2, "the country profile matches BOTH schools' invoices")

    def test_the_report_refuses_without_a_school(self):
        response = self._get(None)
        self.assertEqual(
            response.status_code, 403,
            "no school bound: the report must refuse, as payment_readiness_dashboard does",
        )

    def test_the_report_does_not_carry_another_schools_money(self):
        """Assert the view's COMPUTED arrears, not the rendered markup.

        A substring on the page is not the behaviour: the first version of this
        test matched '987654' against an unrelated '987654321' notification-URL
        placeholder in the shell chrome, and passed for the wrong reason.
        """
        captured = {}

        def _capture(request, template, context):
            captured.update(context)
            return HttpResponse(b"ok")

        with patch("apps.finance.views_reports.render", _capture):
            self._get(self.mine)

        overdue_totals = [row["overdue_total"] for row in captured["overdue"]]
        self.assertNotIn(
            OTHER_SCHOOL_AR, overdue_totals,
            "the rival school's overdue balance reached this school's arrears report",
        )
        self.assertEqual(
            overdue_totals, [MY_AR],
            "the report must show this school's arrears and only this school's",
        )
