"""The cloud must never ship a child row whose parent it cannot supply.

``enrich_delta_rows_with_fk_referents`` attaches the parent rows a delta bundle
implies but does not contain. When it could NOT resolve a parent it used to
``continue`` — silently shipping the child with a reference the box can never
satisfy. On the box that row is written, and because Django defers FK checks on
PostgreSQL the violation lands at COMMIT and takes the ENTIRE pull with it. The
cursor never advances, so the next cycle re-pulls the same doomed bundle: one
unresolvable reference left the box permanently unsynced.

    pull failed: insert or update on table "academics_specialty" violates
    foreign key constraint ... Key (department_id)=(2) is not present in
    table "academics_department".

Dropping the child costs one row and lets the rest of the bundle land, and it
self-heals as soon as the parent becomes syncable.

Note the lookup is school-scoped, so "parent owned by another tenant" is an
unresolvable parent too — pinned below, because that shape needs no data
corruption to occur.
"""
from __future__ import annotations

import uuid

from django.test import TestCase

from apps.academics.models import Department, Specialty
from apps.api.sync_services import (
    _get_entity_config,
    enrich_delta_rows_with_fk_referents,
)
from apps.schools.models import School


def _specialty_row(*, pk, department_id, name="Pure Science", code="PS1"):
    return {
        "entity_type": "specialty",
        "id": pk,
        "client_offline_id": "",
        "changes": {"name": name, "code": code, "department_id": department_id},
        "updated_at": "2026-08-20T08:00:00+00:00",
    }


class UnshippableReferentTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Ship {uid}", slug=f"ship-{uid}", subdomain=f"ship{uid}", is_active=True
        )
        self.other = School.objects.create(
            name=f"Other {uid}", slug=f"oship-{uid}", subdomain=f"osh{uid}", is_active=True
        )
        self.config = _get_entity_config(include_derived=True)

    def _types(self, rows):
        return [(r.get("entity_type"), r.get("id")) for r in rows]

    def test_resolvable_parent_is_attached_and_child_kept(self):
        dept = Department.objects.create(
            school=self.school, name="Sciences", code=f"SCI{uuid.uuid4().hex[:4]}"
        )
        spec = Specialty.objects.create(
            school=self.school, department=dept, name="Pure Science",
            code=f"PS{uuid.uuid4().hex[:4]}",
        )
        rows = [_specialty_row(pk=spec.pk, department_id=dept.pk)]
        out = enrich_delta_rows_with_fk_referents(rows, self.school, self.config)

        kinds = self._types(out)
        self.assertIn(("department", dept.pk), kinds, "parent must ride along")
        self.assertIn(("specialty", spec.pk), kinds, "child must still ship")
        # Parent must come first so the box can apply the child after it.
        self.assertLess(kinds.index(("department", dept.pk)), kinds.index(("specialty", spec.pk)))

    def test_missing_parent_drops_the_child_instead_of_shipping_it_dangling(self):
        rows = [_specialty_row(pk=4242, department_id=999999)]
        out = enrich_delta_rows_with_fk_referents(rows, self.school, self.config)
        self.assertEqual(
            out, [],
            "a child whose parent cannot be supplied must not be shipped — that row "
            "is what aborted the entire pull at COMMIT",
        )

    def test_parent_owned_by_another_school_is_also_unshippable(self):
        foreign = Department.objects.create(
            school=self.other, name="Foreign", code=f"FOR{uuid.uuid4().hex[:4]}"
        )
        rows = [_specialty_row(pk=4243, department_id=foreign.pk)]
        out = enrich_delta_rows_with_fk_referents(rows, self.school, self.config)
        self.assertEqual(
            out, [],
            "the referent lookup is school-scoped, so a cross-tenant parent is "
            "unresolvable and its child must not ship",
        )

    def test_unowned_parent_is_shipped_not_dropped(self):
        """Production shape: Department pk=2 has school_id NULL.

        ``Department.school`` is ``null=True`` and prod carries real unowned rows.
        A strict school-scoped referent lookup can never match one, so the child
        looked unresolvable — it shipped dangling (killing the pull) and, once
        dropping was added, would have silently never synced instead. An unowned
        parent belongs to nobody, so shipping it to this school leaks nothing.
        """
        orphan_dept = Department.objects.create(
            school=None, name="Science", code=f"SCI{uuid.uuid4().hex[:4]}"
        )
        rows = [_specialty_row(pk=4245, department_id=orphan_dept.pk)]
        out = enrich_delta_rows_with_fk_referents(rows, self.school, self.config)

        kinds = self._types(out)
        self.assertIn(("department", orphan_dept.pk), kinds, "unowned parent must ride along")
        self.assertIn(("specialty", 4245), kinds, "child must NOT be dropped")

    def test_unrelated_rows_survive_the_drop(self):
        """Dropping one bad child must not cost the rest of the bundle."""
        dept = Department.objects.create(
            school=self.school, name="Good", code=f"GD{uuid.uuid4().hex[:4]}"
        )
        good = Specialty.objects.create(
            school=self.school, department=dept, name="Good Spec",
            code=f"GS{uuid.uuid4().hex[:4]}",
        )
        rows = [
            _specialty_row(pk=good.pk, department_id=dept.pk),
            _specialty_row(pk=4244, department_id=999999, name="Orphan", code="OR1"),
        ]
        out = enrich_delta_rows_with_fk_referents(rows, self.school, self.config)
        kinds = self._types(out)
        self.assertIn(("specialty", good.pk), kinds)
        self.assertNotIn(("specialty", 4244), kinds)
