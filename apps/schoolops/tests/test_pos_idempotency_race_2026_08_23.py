"""A replayed POS scan must not debit the wallet twice.

``checkout()`` deduped by READING for a prior line with the same
``idempotency_key``. A read cannot see a sibling transaction that has not
committed, so a canteen tablet on flaky wifi retrying one scan into two workers
had both of them pass the check, create lines, and debit the wallet — the
student paid twice for one scan and two rows carried the same key.

``_prior_sale_line_ids`` is patched to return nothing in the race test: that is
exactly what the second worker sees while the first is still uncommitted, and
it is the only way to reproduce a two-worker race inside one test process. The
assertions on the mock call count and on the surviving row count are the vacuity
guard — they prove the second call really did run the insert path (and was
stopped by the index) rather than short-circuiting somewhere earlier.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.schoolops.models import MealPlanBalance, PosSaleLine
from apps.schoolops.pos_checkout import checkout
from apps.schools.models import School


class PosIdempotencyRaceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"IDEM {uid}", slug=f"idem-{uid}", subdomain=f"idem{uid}", is_active=True
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
            school=self.school, student=self.student, meal_plan=None, balance=Decimal("10.00")
        )

    def _sale(self, **over):
        kwargs = dict(
            school_id=self.school.id,
            student=self.student,
            items=[{"label": "Jollof Rice", "unit_price": "5.00", "quantity": 1}],
            idempotency_key="till-1-scan-7",
        )
        kwargs.update(over)
        return checkout(**kwargs)

    def test_replay_that_misses_the_precheck_is_stopped_by_the_index(self):
        first = self._sale()
        self.assertTrue(first["ok"], first)

        # Second worker's view of the world: the winner has not committed yet.
        with mock.patch(
            "apps.schoolops.pos_checkout._prior_sale_line_ids", return_value=[]
        ) as blind:
            second = self._sale()

        self.assertEqual(blind.call_count, 1)  # it really took the insert path
        self.assertTrue(second.get("dedup"), second)
        self.assertEqual(set(second["sale_line_ids"]), set(first["sale_line_ids"]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("5.00"))  # charged ONCE
        self.assertEqual(
            PosSaleLine.objects.filter(
                school=self.school, idempotency_key="till-1-scan-7"
            ).count(),
            1,
        )

    def test_duplicate_key_and_seq_is_refused_by_the_database(self):
        self._sale()
        row = PosSaleLine.objects.get(school=self.school, idempotency_key="till-1-scan-7")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PosSaleLine.objects.create(
                    school=self.school,
                    student=self.student,
                    item_label=row.item_label,
                    quantity=1,
                    unit_price=Decimal("5.00"),
                    idempotency_key="till-1-scan-7",
                    idempotency_seq=row.idempotency_seq,
                )

    def test_a_multi_line_sale_under_one_key_is_still_allowed(self):
        # The constraint is per LINE: one sale writes several rows under one
        # key, and blocking that would break every basket of more than one item.
        res = self._sale(
            items=[
                {"label": "Jollof Rice", "unit_price": "3.00", "quantity": 1},
                {"label": "Bottled Water", "unit_price": "1.00", "quantity": 1},
            ],
            idempotency_key="till-1-scan-8",
        )
        self.assertTrue(res["ok"], res)
        rows = PosSaleLine.objects.filter(
            school=self.school, idempotency_key="till-1-scan-8"
        )
        self.assertEqual(rows.count(), 2)
        self.assertEqual(sorted(r.idempotency_seq for r in rows), [0, 1])
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("6.00"))

    def test_keyless_cash_sales_are_not_constrained(self):
        # The index is partial: anonymous cash lines carry a blank key and many
        # of them must coexist.
        for _ in range(3):
            res = self._sale(
                idempotency_key="",
                items=[{"label": "Bread Roll", "unit_price": "1.00", "quantity": 1}],
            )
            self.assertTrue(res["ok"], res)
        self.assertEqual(
            PosSaleLine.objects.filter(school=self.school, idempotency_key="").count(), 3
        )
