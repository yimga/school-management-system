"""N+1 / query-count REGRESSION guard for the parent family-billing summary hot path.

Metric #17 (Performance). SAFETY NET written by BUILD-D. The parent dashboard renders
the whole-family balance via ``apps.finance.family_billing_aggregator.aggregate_family_balance``
on every load. With the DEFAULT runners it must touch the DB a CONSTANT number of times
regardless of how many children the guardian has or how many invoices each child has.

Audit (as of 2026-06-26, apps/finance/family_billing_aggregator.py):
  * _default_children_runner (line 169): ONE query --
        StudentGuardian.objects.filter(guardian_user_id=...).select_related("student")
  * _default_balance_runner  (line 194): ONE query --
        Invoice.objects.filter(student_id__in=[...]).exclude(status=VOID)
                       .select_related("profile")
The aggregation itself (aggregate_family_balance, line 230) is pure-Python over those
two result sets -- it never queries inside its loop. So the path is ALREADY optimized:
the query count is CONSTANT (2 ORM queries) as children / invoices grow.

These tests pin that with the REAL default runners (no seam-mocking), asserting the
count for a 1-child/1-invoice family EQUALS the count for a 3-child/many-invoice family.
A regression that fetched invoices per-child (a loop of .filter(student=child)) would
make the larger family's count climb and fail.

CI: tagged for the Postgres lane (finance is not in the default postgres glob, so the
tag + a CI wiring follow-up routes it there). Will NOT run in the BUILD-D local env.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.accounts.models import User
from apps.finance.family_billing_aggregator import aggregate_family_balance
from apps.finance.models import ComplianceProfile, Invoice
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.schools.tests.rls_support import enter_rls_bypass_for_test


@tag("tenants_rls")  # routes the file into a Postgres CI lane
class FamilyBillingQueryCountTests(TestCase):
    """aggregate_family_balance (default runners) uses a constant query count."""

    def setUp(self):
        # Postgres-lane routing tag only; not an RLS-isolation test -> run under
        # bypass so bound RLS does not deny the seed rows / reads. See rls_support.
        enter_rls_bypass_for_test(self)
        self.school = School.objects.create(
            name="Family Billing QC",
            slug="family-billing-qc",
            subdomain="family-billing-qc",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Family Billing QC Profile", country_code="CM"
        )
        self.guardian = User.objects.create_user(
            username="fbqc_parent",
            email="fbqc_parent@test.com",
            password="testpass123",
            role=User.Role.PARENT,
        )

    def _make_child(self, code: str) -> StudentProfile:
        student = StudentProfile.objects.create(
            first_name=f"Child{code}",
            last_name=code,
            student_code=f"FBQC-{code}",
            school=self.school,
            is_active=True,
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian,
            student=student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
        )
        return student

    def _make_invoices(self, student: StudentProfile, n: int) -> None:
        for i in range(n):
            Invoice.objects.create(
                school=self.school,
                profile=self.profile,
                student=student,
                status=Invoice.Status.ISSUED,
                total_amount=Decimal("100.00"),
                balance_amount=Decimal("100.00"),
                due_date=date.today() + timedelta(days=30),
            )

    def _count_aggregate_queries(self) -> int:
        with CaptureQueriesContext(connection) as ctx:
            summary = aggregate_family_balance(
                guardian_user_id=self.guardian.id, today=date.today()
            )
            # Touch the materialized rollups so nothing is left lazy.
            _ = summary.family_total_open_balance
            for row in summary.child_rows:
                _ = row.total_balance_open
        return len(ctx.captured_queries)

    def test_query_count_is_constant_as_children_grow(self):
        """1 child/1 invoice vs 3 children/1 invoice each => SAME query count.

        The default balance runner uses a single student_id__in IN-clause, so adding
        children must NOT add queries. A per-child invoice fetch would fail here.
        """
        c1 = self._make_child("A")
        self._make_invoices(c1, 1)
        small = self._count_aggregate_queries()

        c2 = self._make_child("B")
        c3 = self._make_child("C")
        self._make_invoices(c2, 1)
        self._make_invoices(c3, 1)
        large = self._count_aggregate_queries()

        self.assertEqual(
            small,
            large,
            "aggregate_family_balance query count scaled with child count -- "
            f"N+1 regression (1 child: {small} queries, 3 children: {large}). "
            "The default balance runner's student_id__in batch was likely broken.",
        )

    def test_query_count_is_constant_as_invoices_grow(self):
        """Same single child, 1 invoice vs 5 invoices => SAME query count."""
        c1 = self._make_child("A")
        self._make_invoices(c1, 1)
        small = self._count_aggregate_queries()

        self._make_invoices(c1, 4)  # now 5 total
        large = self._count_aggregate_queries()

        self.assertEqual(
            small,
            large,
            "aggregate_family_balance query count scaled with invoice count -- "
            f"N+1 regression (1 invoice: {small} queries, 5 invoices: {large}).",
        )

    def test_default_runners_use_small_fixed_query_budget(self):
        """Absolute ceiling: the two default runners are exactly two ORM queries.

        Allow a small margin (4) for any framework/savepoint queries so the gate
        stays robust, while still catching a per-child or per-invoice N+1.
        """
        for code in ("A", "B", "C"):
            child = self._make_child(code)
            self._make_invoices(child, 3)

        count = self._count_aggregate_queries()
        self.assertLessEqual(
            count,
            4,
            f"aggregate_family_balance used {count} queries for a 3-child/9-invoice "
            "family; expected ~2 (children + invoices). A per-child/invoice N+1 "
            "would blow this ceiling.",
        )
