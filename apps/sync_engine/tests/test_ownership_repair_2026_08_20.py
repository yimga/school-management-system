"""Unowned rows are invisible to sync — and must be claimed only on evidence.

``build_edge_delta_rows`` ships ``model.objects.filter(school=school)``. A row
with ``school_id`` NULL matches that for NO school, so it can never reach any
box. Production had exactly this: 4/4 departments and 7/7 specialties unowned,
so a tenant's whole curriculum was structurally unsyncable while looking fine.

Repair has to be conservative in one specific direction: claiming a row for the
wrong tenant is a data leak, which is worse than a row that does not sync. So a
row is claimed only when the rows REFERENCING it all point at one school.
Anything foreign or ambiguous is reported and left alone.
"""
from __future__ import annotations

import uuid

from django.test import TestCase

from apps.academics.models import Department, Specialty
from apps.schools.models import School
from apps.sync_engine.ownership_repair import (
    AMBIGUOUS,
    ASSIGNABLE,
    FOREIGN,
    ORPHAN,
    apply_ownership_repair,
    plan_ownership_repair,
)


class OwnershipRepairTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Own {uid}", slug=f"own-{uid}", subdomain=f"own{uid}", is_active=True
        )
        self.other = School.objects.create(
            name=f"Oth {uid}", slug=f"oth-{uid}", subdomain=f"oth{uid}", is_active=True
        )

    def _verdict(self, plan, pk):
        for c in plan["candidates"]:
            if c.pk == pk:
                return c.verdict
        return None

    def test_unowned_row_referenced_only_by_this_school_is_assignable(self):
        dept = Department.objects.create(school=None, name="Sci", code=f"S{uuid.uuid4().hex[:5]}")
        # A specialty OWNED by this school points at the unowned department.
        Specialty.objects.create(
            school=self.school, department=dept, name="Pure",
            code=f"P{uuid.uuid4().hex[:5]}",
        )
        plan = plan_ownership_repair(self.school)
        self.assertEqual(self._verdict(plan, dept.pk), ASSIGNABLE)

        apply_ownership_repair(self.school, plan=plan)
        dept.refresh_from_db()
        self.assertEqual(dept.school_id, self.school.pk, "provable owner must be claimed")

    def test_row_referenced_only_by_another_school_is_never_claimed(self):
        dept = Department.objects.create(school=None, name="For", code=f"F{uuid.uuid4().hex[:5]}")
        Specialty.objects.create(
            school=self.other, department=dept, name="Theirs",
            code=f"T{uuid.uuid4().hex[:5]}",
        )
        plan = plan_ownership_repair(self.school)
        self.assertEqual(self._verdict(plan, dept.pk), FOREIGN)

        apply_ownership_repair(self.school, plan=plan)
        dept.refresh_from_db()
        self.assertIsNone(dept.school_id, "claiming another tenant's row would be a leak")

    def test_row_referenced_by_both_is_ambiguous_and_left_alone(self):
        dept = Department.objects.create(school=None, name="Amb", code=f"A{uuid.uuid4().hex[:5]}")
        Specialty.objects.create(
            school=self.school, department=dept, name="Mine", code=f"M{uuid.uuid4().hex[:5]}"
        )
        Specialty.objects.create(
            school=self.other, department=dept, name="Yours", code=f"Y{uuid.uuid4().hex[:5]}"
        )
        plan = plan_ownership_repair(self.school)
        self.assertEqual(self._verdict(plan, dept.pk), AMBIGUOUS)

        apply_ownership_repair(self.school, plan=plan)
        dept.refresh_from_db()
        self.assertIsNone(dept.school_id, "shared-looking rows need a human, not a guess")

    def test_orphan_needs_explicit_opt_in(self):
        dept = Department.objects.create(school=None, name="Orph", code=f"O{uuid.uuid4().hex[:5]}")
        plan = plan_ownership_repair(self.school)
        self.assertEqual(self._verdict(plan, dept.pk), ORPHAN)

        apply_ownership_repair(self.school, plan=plan)
        dept.refresh_from_db()
        self.assertIsNone(dept.school_id, "no evidence => not claimed by default")

        apply_ownership_repair(self.school, include_orphans=True)
        dept.refresh_from_db()
        self.assertEqual(dept.school_id, self.school.pk, "explicit opt-in claims it")

    def test_already_owned_rows_are_not_candidates(self):
        owned = Department.objects.create(
            school=self.other, name="Owned", code=f"W{uuid.uuid4().hex[:5]}"
        )
        plan = plan_ownership_repair(self.school)
        self.assertIsNone(self._verdict(plan, owned.pk), "audit only considers unowned rows")
