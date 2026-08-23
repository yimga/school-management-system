"""The allergen sale-block must survive the way a canteen names its items.

``allergen_conflict`` compared whole lowercase tokens for exact equality, so a
milk-allergic child could be sold a "Chocolate Milkshake" and a peanut-allergic
child a bag of "Peanuts" — the plural and the compound are simply different
tokens. This is the child-safety barrier the POS README defaults ON, so a miss
here is a sale that should never have completed.

The negative cases below are the vacuity guard in reverse: they pin that the
looser matcher does NOT start blocking unrelated menu items (a 3-letter noise
token like "raw" is a substring of "strawberry"), so a green run means the
matcher got wider in the right direction only.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.schoolops.models import HealthRecord, MealPlanBalance, PosSaleLine
from apps.schoolops.pos_checkout import allergen_conflict, checkout
from apps.schools.models import School


class AllergenPluralAndCompoundTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"ALG {uid}", slug=f"alg-{uid}", subdomain=f"alg{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="C1", code=f"C{uid}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            first_name="S",
            last_name="T",
            date_of_birth="2012-01-01",
            student_code=f"BADGE{uid}",
            school=self.school,
            classroom=classroom,
        )
        self.wallet = MealPlanBalance.objects.create(
            school=self.school, student=self.student, meal_plan=None, balance=Decimal("20.00")
        )

    def _note(self, text):
        HealthRecord.objects.create(
            school=self.school,
            student=self.student,
            record_type="allergy",
            notes=text,
        )

    def test_compound_item_name_conflicts(self):
        self._note("Severe milk allergy")
        self.assertEqual(allergen_conflict(self.student, "Chocolate Milkshake"), "milk")

    def test_plural_item_name_conflicts(self):
        self._note("Peanut allergy")
        self.assertEqual(allergen_conflict(self.student, "Salted Peanuts"), "peanut")

    def test_plural_allergen_term_matches_singular_item(self):
        self._note("Allergic to eggs")
        self.assertEqual(allergen_conflict(self.student, "Egg Sandwich"), "eggs")

    def test_unrelated_items_are_still_sellable(self):
        # A 3-letter fragment must not turn into a menu-wide block:
        # "raw" is a substring of "strawberry", "nut" of "doughnut".
        self._note("No raw milk. Nut allergy.")
        self.assertIsNone(allergen_conflict(self.student, "Strawberry Yoghurt"))
        self.assertIsNone(allergen_conflict(self.student, "Bottled Water"))

    def test_checkout_refuses_the_compound_item_and_leaves_the_wallet_alone(self):
        self._note("Severe milk allergy")
        res = checkout(
            school_id=self.school.id,
            student=self.student,
            items=[{"label": "Chocolate Milkshake", "unit_price": "2.50", "quantity": 1}],
        )
        self.assertFalse(res["ok"], res)
        self.assertTrue(res["blocked"])
        self.assertIn("milk", res["reason"].lower())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("20.00"))
        self.assertEqual(PosSaleLine.objects.filter(student=self.student).count(), 0)
