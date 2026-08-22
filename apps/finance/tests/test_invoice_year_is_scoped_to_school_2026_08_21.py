"""The academic year an invoice run bills against must belong to the school billed.

`_auto_generate_fee_invoices_body` resolved the year with an unscoped
`get_current_academic_year()` and only then worked out which school it was billing.
Under RLS mode (one database, every tenant's rows in the same tables — what
`USE_DJANGO_TENANTS=0` gives, and what the local and CI suites run) those two lookups
can disagree, and the year is not cosmetic: it selects the fee plans to invoice
(`FeePlan.objects.filter(academic_year=current_year)`) and the billing period the run
is deduplicated on.

The assertion is deliberately about the ORDER of resolution rather than about an
invoice row: reaching real invoice generation needs a compliance profile, fee plans,
enrolments and a due schedule, and a test that has to build all of that to observe a
two-line ordering bug is a test nobody trusts when it goes red.
"""

from __future__ import annotations

import ast
import inspect
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.automation.helpers import get_current_academic_year, get_current_term
from apps.schools.models import School


class InvoiceYearScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.now().date()
        # Created first, so an unscoped "first active year" lookup finds THIS one.
        cls.other = School.objects.create(
            name="Other Finance School",
            slug="fin-other",
            subdomain="fin-other",
            is_active=True,
        )
        cls.other_year = AcademicYear.objects.create(
            school=cls.other,
            name="Other 2026/2027",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=300),
            is_active=True,
        )
        cls.billed = School.objects.create(
            name="Billed Finance School",
            slug="fin-billed",
            subdomain="fin-billed",
            is_active=True,
        )
        cls.billed_year = AcademicYear.objects.create(
            school=cls.billed,
            name="Billed 2026/2027",
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=300),
            is_active=True,
        )

    def test_unscoped_lookup_really_can_return_the_wrong_schools_year(self):
        """Establishes the hazard is real here, not hypothetical."""
        unscoped = get_current_academic_year()
        self.assertIsNotNone(unscoped)
        self.assertIn(unscoped.pk, {self.other_year.pk, self.billed_year.pk})
        # Whichever it picked, it is the wrong answer for one of the two schools.
        wrong_for = self.billed if unscoped.pk == self.other_year.pk else self.other
        self.assertNotEqual(
            unscoped.school_id,
            wrong_for.pk,
            "fixture assumption broken: the two schools must have distinct years",
        )

    def test_scoped_lookup_returns_each_schools_own_year(self):
        self.assertEqual(
            get_current_academic_year(school=self.billed).pk, self.billed_year.pk
        )
        self.assertEqual(
            get_current_academic_year(school=self.other).pk, self.other_year.pk
        )

    def test_scoped_term_lookup_stays_within_the_schools_year(self):
        from apps.academics.models import Term

        today = timezone.now().date()
        mine = Term.objects.create(
            school=self.billed,
            academic_year=self.billed_year,
            name="FIRST",
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=60),
            is_active=True,
        )
        Term.objects.create(
            school=self.other,
            academic_year=self.other_year,
            name="FIRST",
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=60),
            is_active=True,
        )
        self.assertEqual(
            get_current_term(self.billed_year, school=self.billed).pk, mine.pk
        )

    def test_invoice_task_resolves_the_school_before_the_year(self):
        """The ordering fix itself, asserted where the bug lived."""
        from apps.finance import tasks

        source = inspect.getsource(tasks._auto_generate_fee_invoices_body)
        tree = ast.parse(source.lstrip())
        func = tree.body[0]

        school_bound_at = None
        year_called_at = None
        for node in ast.walk(func):
            if (
                isinstance(node, ast.Name)
                and isinstance(node.ctx, ast.Store)
                and node.id == "school"
                and school_bound_at is None
            ):
                school_bound_at = node.lineno
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_current_academic_year"
            ):
                year_called_at = node.lineno
                self.assertIn(
                    "school",
                    [kw.arg for kw in node.keywords],
                    "the invoice run must scope the academic year to the school it "
                    "is billing; an unscoped lookup can return another tenant's year",
                )

        self.assertIsNotNone(school_bound_at, "school is never resolved in this task")
        self.assertIsNotNone(year_called_at, "the task no longer resolves a year")
        self.assertLess(
            school_bound_at,
            year_called_at,
            "school must be resolved BEFORE the academic year it is billed against",
        )

    def test_invoice_task_also_scopes_the_term(self):
        from apps.finance import tasks

        tree = ast.parse(inspect.getsource(tasks._auto_generate_fee_invoices_body).lstrip())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_current_term"
            ):
                self.assertIn("school", [kw.arg for kw in node.keywords])
                return
        self.fail("the invoice task no longer resolves a term")
