"""A row that changes nothing is not a conflict, and not a missing reference either.

WHAT WENT WRONG. ``_apply_changes_inner`` graded a conflict on TIMESTAMPS alone, and it
did so 130 lines before the check that asks whether the incoming row would change
anything. The no-op check could therefore never run on a row the grading had already
refused -- and on a box the grading is rigged against every row it looks at:

    the cloud sends department #7 with updated_at = T0
    the box applied it earlier, so its own row carries updated_at = T1 (auto_now)
    T1 > T0 by construction, so "the client is stale" -- conflict

The engine has a provenance guard for exactly this (SyncApplyLedger, and its comment says
it was written after a retry "manufactured SyncConflict rows out of the engine's own
writes"). It works, for rows SYNC wrote. It cannot work for rows the provisioning CLONE
wrote, because those have no ledger entry -- and on a freshly cloned box that is nearly
every row. One full-corpus re-pull then filed a conflict against every already-converged
row on the rail, each one asking an operator to choose between a value and itself.

The FK preflight sat in the same trap: an UNCHANGED row was refused as
``missing_reference`` over a parent it was never going to write, and that refusal is what
rewinds the pull cursor for a full-corpus replay -- which re-offers every row again. The
replay fed the conflicts.

THE FIX IS AN ORDERING, NOT A NEW RULE. If no value changes, nothing is written: there is
no conflict to adjudicate and no constraint to violate. So the no-op check moved above
both. ``_same_value`` fails toward CHANGED for anything that is not a plain scalar, so the
move can only ever suppress a decision about values that are already identical -- which is
what the tests below pin from both sides.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.accounts.models import User
from apps.api.sync_services import _get_entity_config, apply_changes
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import SyncConflict
from apps.sync_engine.models import SyncApplyLedger

# Deliberately old: older than anything auto_now will stamp on a row created in setUp,
# which is the whole point -- the cloud's copy of an already-converged row always looks
# stale to the box that applied it.
STALE = "2026-01-01T00:00:00+00:00"


def _row(entity_type, pk, changes, *, updated_at=STALE):
    """A bundle row as the operator's download endpoint emits it (cloud-authored)."""
    return {
        "entity_type": entity_type,
        "id": pk,
        "client_offline_id": "",
        "changes": changes,
        "updated_at": updated_at,
    }


class _Fixture(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Noop {uid}", slug=f"noop-{uid}", subdomain=f"noop{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"noop_{uid}", password="Test1234", email=f"n{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department.objects.create(
            school=self.school, name="Sciences", code=f"SCI-{uid}"
        )
        # `classroom` is one of the ORIGINAL three entities, so it is the only kind of row
        # the ONLINE registry (sync_origin=None) can carry -- `department` is derived and
        # an online caller is answered 400 for it by design. Tests that assert on the
        # online path therefore have to use this one, or they pass without exercising
        # anything.
        self.year = AcademicYear.objects.create(
            school=self.school, name=f"Year {uid}",
            start_date="2026-09-01", end_date="2027-07-31",
        )
        self.classroom = Classroom.objects.create(
            school=self.school, name="Form One", code=f"F1-{uid}",
            department=self.dept, academic_year=self.year,
        )
        # The values the assertions below depend on, asserted rather than assumed: if
        # `name` ever leaves either set these tests would pass while testing nothing.
        _model, derived_allowed = _get_entity_config(include_derived=True)["department"]
        self.assertIn("name", derived_allowed)
        _model, online_allowed = _get_entity_config(include_derived=False)["classroom"]
        self.assertIn("name", online_allowed)

    def _apply(self, rows, *, origin="cloud-pull"):
        return apply_changes(str(self.school.id), self.user, rows, sync_origin=origin)


class TheEngineMustNotFileAConflictAgainstItselfTests(_Fixture):
    """The 68k-record failure, reproduced at its root and pinned shut."""

    def test_an_identical_row_with_an_older_stamp_lands_instead_of_conflicting(self):
        # No SyncApplyLedger row exists for this department -- it stands in for a row the
        # provisioning clone wrote, which is the case the provenance guard cannot cover.
        self.assertFalse(
            SyncApplyLedger.objects.filter(school=self.school, entity_type="department").exists()
        )
        out = self._apply([_row("department", self.dept.pk, {"name": "Sciences"})])

        self.assertEqual(out["conflicts"], [])
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 0)
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertTrue(out["results"][0]["data"]["unchanged"])
        self.assertEqual(out["success_count"], 1)

    def test_the_row_is_not_rewritten_so_its_stamp_does_not_move(self):
        # Landing a no-op by SAVING it would bump updated_at and re-enter the row into the
        # next delta going the other way -- churn manufactured by the fix for churn.
        before = Department.objects.get(pk=self.dept.pk).updated_at
        self._apply([_row("department", self.dept.pk, {"name": "Sciences"})])
        self.assertEqual(Department.objects.get(pk=self.dept.pk).updated_at, before)

    def test_the_no_op_still_records_provenance(self):
        # Without the ledger row the box would push this row straight back up.
        self._apply([_row("department", self.dept.pk, {"name": "Sciences"})])
        self.assertTrue(
            SyncApplyLedger.objects.filter(
                school=self.school, entity_type="department", local_pk=str(self.dept.pk)
            ).exists()
        )

    def test_an_online_edit_records_no_provenance(self):
        # sync_origin=None is a human at a keyboard, not the rail. Recording provenance
        # there would suppress a genuine local edit from ever propagating.
        out = self._apply(
            [_row("classroom", self.classroom.pk, {"name": "Form One"})], origin=None
        )
        # Assert it actually LANDED first. An entity the online registry does not carry is
        # answered 400, which would also leave the ledger empty -- and this test would
        # then pass while proving nothing about provenance.
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertFalse(
            SyncApplyLedger.objects.filter(school=self.school, entity_type="classroom").exists()
        )


class ARealDisagreementMustStillBeAConflictTests(_Fixture):
    """The other half. A fix that also swallowed real conflicts would be worse."""

    def test_a_stale_row_carrying_a_different_value_still_conflicts(self):
        out = self._apply([_row("department", self.dept.pk, {"name": "Renamed"})])

        self.assertEqual(len(out["conflicts"]), 1)
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "conflict")
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 1)
        # And the box's value is kept, which is what "conflict" is supposed to mean.
        self.assertEqual(Department.objects.get(pk=self.dept.pk).name, "Sciences")

    def test_a_newer_row_carrying_a_different_value_applies(self):
        out = self._apply(
            [
                _row(
                    "department",
                    self.dept.pk,
                    {"name": "Renamed"},
                    updated_at="2099-01-01T00:00:00+00:00",
                )
            ]
        )
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertEqual(Department.objects.get(pk=self.dept.pk).name, "Renamed")


class TheOrderingItselfIsTheFixTests(_Fixture):
    """Pin the ORDER, not just its consequence.

    The two classes above would also pass if the no-op check merely ran before the
    conflict was PERSISTED. What actually changed is that it runs before the referential
    preflight as well, and that is the half which stops the replay loop -- so it is
    asserted directly, by making the preflight refuse everything and checking which rows
    still get through.
    """

    def _always_missing(self):
        return mock.patch(
            "apps.api.sync_services._unresolvable_fk",
            return_value=("department_id", "academics.Department", 999999),
        )

    def test_an_unchanged_row_is_not_refused_by_the_fk_preflight(self):
        with self._always_missing():
            out = self._apply([_row("department", self.dept.pk, {"name": "Sciences"})])
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertTrue(out["results"][0]["data"]["unchanged"])

    def test_a_changed_row_is_still_refused_by_the_fk_preflight(self):
        with self._always_missing():
            out = self._apply([_row("department", self.dept.pk, {"name": "Renamed"},
                                    updated_at="2099-01-01T00:00:00+00:00")])
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "missing_reference")
        self.assertEqual(out["results"][0]["data"]["references"], "academics.Department")

    def test_the_missing_reference_report_names_the_parent_model(self):
        # sync_runner decides whether to rewind the pull cursor from this label, so the
        # field has to be present and has to be the model label, not a message.
        with self._always_missing():
            out = self._apply([_row("department", self.dept.pk, {"name": "Renamed"},
                                    updated_at="2099-01-01T00:00:00+00:00")])
        self.assertEqual(
            set(out["results"][0]["data"]),
            {"error", "field", "references", "referenced_id"},
        )


class TheGuardMustNotDependOnTheDirectionTests(_Fixture):
    """The provenance guard only covers cloud-pull. The no-op check covers both.

    A cloud receiving an edge push runs the same function with sync_origin="edge-push",
    where `_sync_applied` is never even loaded -- so before this change the cloud had no
    protection at all against a row being re-offered unchanged.
    """

    def test_an_identical_row_pushed_upward_also_lands_instead_of_conflicting(self):
        out = self._apply(
            [_row("department", self.dept.pk, {"name": "Sciences"})], origin="edge-push"
        )
        self.assertEqual(out["conflicts"], [])
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 0)

    def test_an_identical_row_from_an_online_edit_also_lands(self):
        out = self._apply(
            [_row("classroom", self.classroom.pk, {"name": "Form One"})], origin=None
        )
        self.assertEqual(out["conflicts"], [])
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertTrue(out["results"][0]["data"]["unchanged"])
