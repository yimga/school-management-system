"""First-run FeePlan seeding: a fresh tenant must get one editable, zero-amount
starter plan so the Fees surface is not blank and auto-invoicing does not dead-end
on ``{"status": "no_plans"}`` (the lived-experience gap-doc's day-one P0).

MUST-FIRE: against the pre-fix tree ``ensure_tenant_default_fee_plan`` does not exist,
so importing this module raises ``ImportError`` and every test errors.
"""

from datetime import date
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import FeeItem, FeePlan
from apps.finance.provisioning_seed import ensure_tenant_default_fee_plan
from apps.schools.models import School


class DefaultFeePlanSeedTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Seed FeePlan School",
            slug="seed-feeplan-school",
            subdomain="seed-feeplan-school",
            country_code="CM",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2026-2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_active=True,
        )
        self.department = Department.objects.create(
            school=self.school, name="Science", code="SCI"
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.department,
            name="General",
            code="GEN",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.department,
            name="Form 1",
            code="F1",
        )

    def test_seeds_zero_amount_starter_plan_when_none_exist(self):
        plan = ensure_tenant_default_fee_plan(self.school, academic_year=self.year)

        self.assertIsNotNone(plan)
        # The dead-end this fixes: an active plan now exists for the active year, so
        # auto_generate_fee_invoices_task no longer returns {"status": "no_plans"}.
        self.assertTrue(
            FeePlan.objects.filter(academic_year=self.year, is_active=True).exists()
        )
        self.assertEqual(self.year.fee_plans.count(), 1)
        self.assertTrue(plan.is_active)

        items = list(plan.items.all())
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.item_type, FeeItem.ItemType.TUITION)
        # Zero amount by design — nothing is charged until the school sets it.
        self.assertEqual(item.amount, Decimal("0"))
        self.assertTrue(item.is_mandatory)

    def test_idempotent_no_duplicate_on_rerun(self):
        first = ensure_tenant_default_fee_plan(self.school, academic_year=self.year)
        self.assertIsNotNone(first)

        # A provisioning retry / reconcile sweep must not add a second plan or item.
        second = ensure_tenant_default_fee_plan(self.school, academic_year=self.year)
        self.assertIsNone(second)
        self.assertEqual(self.year.fee_plans.count(), 1)
        self.assertEqual(first.items.count(), 1)

    def test_skips_when_operator_already_has_a_plan(self):
        # Operator created their own plan first; the seeder must not touch it or add a
        # stray "Default Tuition Plan" alongside.
        operator_plan = FeePlan.objects.create(
            school=self.school,
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            name="Annual Tuition (operator)",
        )
        result = ensure_tenant_default_fee_plan(self.school, academic_year=self.year)

        self.assertIsNone(result)
        self.assertEqual(self.year.fee_plans.count(), 1)
        self.assertEqual(self.year.fee_plans.first().pk, operator_plan.pk)

    def test_returns_none_without_classroom_or_specialty(self):
        # A year whose academic skeleton is not seeded yet (mid-provision) declines.
        empty_year = AcademicYear.objects.create(
            school=self.school,
            name="2027-2028",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_active=False,
        )
        # No classroom for empty_year -> declines even though a specialty exists.
        result = ensure_tenant_default_fee_plan(self.school, academic_year=empty_year)
        self.assertIsNone(result)
        self.assertEqual(empty_year.fee_plans.count(), 0)

    def test_returns_none_when_academic_year_missing(self):
        self.assertIsNone(
            ensure_tenant_default_fee_plan(self.school, academic_year=None)
        )
