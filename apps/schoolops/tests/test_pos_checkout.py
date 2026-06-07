"""Wave C — cashless campus POS checkout + allergen barrier.

Resolve student → enforce allergen block → debit MealPlanBalance atomically →
record a student-linked, idempotent PosSaleLine.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.schoolops.models import HealthRecord, MealPlanBalance, PosSaleLine
from apps.schoolops.pos_checkout import (
    allergen_conflict,
    checkout,
    resolve_student_for_credential,
    student_allergen_terms,
)
from apps.schools.models import School


class PosCheckoutTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"POS {uid}", slug=f"pos-{uid}", subdomain=f"pos{uid}", is_active=True
        )
        self.user = User.objects.create_user(username=f"cash_{uid}", password="x")
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
        HealthRecord.objects.create(
            school=self.school,
            student=self.student,
            record_type="allergy",
            notes="Peanut allergy, severe. Avoid all nuts.",
        )

    # --- pure helpers ---
    def test_allergen_terms_extracted(self):
        terms = student_allergen_terms(self.student)
        self.assertIn("peanut", terms)
        self.assertNotIn("allergy", terms)  # stopword dropped

    def test_allergen_conflict_matches_label(self):
        self.assertEqual(allergen_conflict(self.student, "Peanut Bar"), "peanut")
        self.assertIsNone(allergen_conflict(self.student, "Bottled Water"))

    def test_resolve_by_credential_code(self):
        found = resolve_student_for_credential(self.school.id, credential=self.student.student_code)
        self.assertEqual(found.pk, self.student.pk)
        self.assertIsNone(resolve_student_for_credential(self.school.id, credential="NOPE"))

    # --- checkout behaviour ---
    def test_allergen_block_prevents_sale_and_debit(self):
        res = checkout(
            school_id=self.school.id,
            student=self.student,
            items=[{"label": "Peanut Bar", "unit_price": "2.00", "quantity": 1}],
        )
        self.assertFalse(res["ok"])
        self.assertTrue(res["blocked"])
        self.assertIn("peanut", res["reason"].lower())
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("20.00"))  # untouched
        self.assertEqual(PosSaleLine.objects.filter(student=self.student).count(), 0)

    def test_insufficient_balance_blocks(self):
        res = checkout(
            school_id=self.school.id,
            student=self.student,
            items=[{"label": "Laptop", "unit_price": "50.00", "quantity": 1}],
        )
        self.assertFalse(res["ok"])
        self.assertTrue(res["insufficient"])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("20.00"))

    def test_successful_purchase_debits_wallet(self):
        res = checkout(
            school_id=self.school.id,
            student=self.student,
            cashier_user_id=self.user.id,
            items=[
                {"label": "Bottled Water", "unit_price": "1.50", "quantity": 2},
                {"label": "Apple", "unit_price": "1.00", "quantity": 1},
            ],
        )
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["charged"], "4.00")
        self.assertEqual(res["new_balance"], "16.00")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("16.00"))
        lines = PosSaleLine.objects.filter(student=self.student)
        self.assertEqual(lines.count(), 2)
        self.assertEqual(lines.first().recorded_by_id, self.user.id)

    def test_idempotent_no_double_charge(self):
        kwargs = dict(
            school_id=self.school.id,
            student=self.student,
            items=[{"label": "Juice", "unit_price": "3.00", "quantity": 1}],
            idempotency_key="till-1-txn-42",
        )
        r1 = checkout(**kwargs)
        r2 = checkout(**kwargs)
        self.assertTrue(r1["ok"])
        self.assertTrue(r2.get("dedup"))
        self.assertEqual(set(r1["sale_line_ids"]), set(r2["sale_line_ids"]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("17.00"))  # charged once

    def test_allergen_enforcement_can_be_disabled(self):
        res = checkout(
            school_id=self.school.id,
            student=self.student,
            items=[{"label": "Peanut Bar", "unit_price": "2.00", "quantity": 1}],
            enforce_allergen=False,
        )
        self.assertTrue(res["ok"], res)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("18.00"))
