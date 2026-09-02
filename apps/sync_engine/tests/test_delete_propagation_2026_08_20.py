"""G1: a deletion is the one change the engine could not carry. Now it can.

THE GAP. The delta is built by scanning ``filter(updated_at__gt=since)``. A deleted row
leaves nothing to scan, so its absence never reached the other side. A student withdrawn
on the cloud stayed enrolled on the appliance; a classroom removed on the appliance came
back on the next pull, because the cloud's copy was simply re-offered and re-created. No
error was raised in either direction — the sides diverged and every status read green.

WHAT IS PROVEN HERE, in the order that matters:

  * a deletion reaches the far side within one cycle, and stays gone (the row is not
    resurrected by the very next bundle);
  * a deletion of a MONEY / GRADE entity travelling UPWARD is refused, and the cloud
    re-asserts its row so the appliance gets it back instead of the two diverging;
  * an ONLINE_REQUIRED domain is never deleted through the rail at all;
  * delete-dominance against a concurrent edit resolves to the SAME answer no matter
    which side is asked first — the property that makes convergence a fact rather than a
    coincidence of ordering;
  * a resurrection (a strictly newer write) beats an older burial, so a delete is not a
    permanent ban on a pk;
  * the flood guard refuses a bundle that would mirror a mass wipe;
  * the kill switch genuinely restores the previous behaviour.
"""
from __future__ import annotations

import datetime as dt

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import Classroom, Department, Specialty
from apps.accounts.models import User
from apps.api.sync_services import apply_changes, apply_deletes, apply_edge_inserts
from apps.schools.models import School
from apps.sync_engine.edge_inbox import split_bundle_rows
from apps.sync_engine.edge_outbox import build_edge_delta_rows
from apps.sync_engine.models import SyncTombstone, record_sync_apply
from apps.sync_engine.tombstones import (
    DELETE_OP,
    prune_tombstones,
    record_tombstone,
    tombstone_index,
)


def _delete_row(entity_type, pk, when, *, client_offline_id=""):
    """A deletion exactly as the delta builder emits it onto the wire."""
    return {
        "entity_type": entity_type,
        "id": str(pk),
        "client_offline_id": client_offline_id,
        "op": DELETE_OP,
        "changes": {},
        "updated_at": when.isoformat(),
    }


def _update_row(entity_type, pk, changes, when, *, client_offline_id=""):
    return {
        "entity_type": entity_type,
        "id": pk,
        "client_offline_id": client_offline_id,
        "changes": changes,
        "updated_at": when.isoformat(),
    }


class _Fixture(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Tomb School", slug="tomb-school", subdomain="tomb-school"
        )
        self.admin = User.objects.create_user(
            username="tomb-admin", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        self.dept = self._cloud_authored(
            "department",
            Department.objects.create(school=self.school, name="Trades", code="TRD"),
        )

    def _cloud_authored(self, entity_type, obj):
        """Leave behind what a row the FAR SIDE authored leaves behind on this side.

        These tests delete by pk alone, which is how the cloud names a row it created:
        ``_create_from_cloud_pull`` creates such a row AT THE OPERATOR'S PK and records
        the apply, and ``apply_changes`` records one for every row this side has taken an
        update from. That ledger entry is the evidence ``apply_deletes`` now requires
        before a pk-only deletion may destroy a LIVE local row - see
        :mod:`apps.sync_engine.delete_safety`.

        A row a test merely creates has none, and is indistinguishable from one an admin
        typed into the box's own form: anchor-less and box-pk'd. That is precisely the
        row a far-side integer must not be allowed to delete, so a test that means
        "cloud-authored" now has to say so rather than borrow the old rail's assumption.
        """
        record_sync_apply(
            str(self.school.id), entity_type, obj.pk,
            getattr(obj, "updated_at", None), "cloud-pull",
        )
        return obj

    def _pull(self, rows):
        return apply_deletes(str(self.school.id), self.admin, rows, sync_origin="cloud-pull")

    def _push(self, rows):
        return apply_deletes(str(self.school.id), self.admin, rows, sync_origin="edge-push")


# --------------------------------------------------------------------------- #
# The receiver: a deletion actually lands
# --------------------------------------------------------------------------- #
class DeletionCrossesTheBoundaryTests(_Fixture):
    def test_a_deleted_row_is_removed_on_this_side(self):
        pk = self.dept.pk
        out = self._pull([_delete_row("department", pk, timezone.now())])

        self.assertEqual(out["deleted"], 1)
        self.assertEqual(out["results"][0]["status"], 200)
        self.assertFalse(Department.objects.filter(pk=pk).exists())

    def test_applying_a_deletion_records_the_burial_with_the_ORIGINAL_time(self):
        """The original timestamp is what makes dominance order-independent. Stamping
        `now` instead would make the answer depend on when each side happened to sync."""
        when = timezone.now() - dt.timedelta(hours=3)
        self._pull([_delete_row("department", self.dept.pk, when)])

        tomb = SyncTombstone.objects.get(
            school=self.school, entity_type="department", local_pk=str(self.dept.pk)
        )
        self.assertEqual(tomb.deleted_at, when)
        self.assertEqual(tomb.origin, "cloud-pull")

    def test_a_row_that_is_already_absent_is_still_recorded_as_buried(self):
        """Otherwise the next bundle re-creates it: the far side keeps offering the row
        (its updated_at is older than our cursor) and nothing here remembers it is gone."""
        ghost = self.dept.pk + 5_000
        out = self._pull([_delete_row("department", ghost, timezone.now())])

        self.assertEqual(out["results"][0]["data"], {"deleted": False, "already_absent": True})
        self.assertTrue(
            SyncTombstone.objects.filter(entity_type="department", local_pk=str(ghost)).exists()
        )

    def test_deleting_one_row_does_not_stop_the_rest_of_the_batch(self):
        other = self._cloud_authored(
            "department",
            Department.objects.create(school=self.school, name="Other", code="OTH"),
        )
        rows = [
            _delete_row("nonsense_entity", 1, timezone.now()),
            _delete_row("department", other.pk, timezone.now()),
        ]
        out = self._pull(rows)
        self.assertEqual(out["results"][0]["status"], 400)
        self.assertEqual(out["results"][1]["status"], 200)
        self.assertFalse(Department.objects.filter(pk=other.pk).exists())


# --------------------------------------------------------------------------- #
# The sender: a local delete becomes a wire row
# --------------------------------------------------------------------------- #
class DeletionEntersTheDeltaTests(_Fixture):
    def test_deleting_a_row_locally_emits_a_delete_row_in_the_next_delta(self):
        pk = self.dept.pk
        self.dept.delete()

        rows, meta = build_edge_delta_rows(self.school)
        deletes = [r for r in rows if r.get("op") == DELETE_OP]
        self.assertEqual(
            [r["id"] for r in deletes],
            [str(pk)],
            "the deletion never reached the wire, so the far side keeps the row forever",
        )
        self.assertIsNotNone(meta["high_water"])

    def test_a_cascade_delete_also_travels(self):
        """The common way rows actually disappear. No `is_deleted` column would ever be
        set by a database cascade, which is why this rides post_delete instead."""
        from apps.academics.models import Subject, SpecialtySubject

        spec = Specialty.objects.create(
            school=self.school, department=self.dept, name="Masonry", code="MAS-C"
        )
        subject = Subject.objects.create(school=self.school, name="Bricklaying", code="BRK-C")
        link = SpecialtySubject.objects.create(
            school=self.school, specialty=spec, subject=subject
        )
        link_pk, spec_pk = link.pk, spec.pk
        spec.delete()  # CASCADEs to the curriculum link

        rows, _meta = build_edge_delta_rows(self.school)
        deleted_ids = {(r["entity_type"], r["id"]) for r in rows if r.get("op") == DELETE_OP}
        self.assertIn(("specialty_subject", str(link_pk)), deleted_ids)
        self.assertIn(("specialty", str(spec_pk)), deleted_ids)

    def test_a_deletion_the_local_schema_refuses_degrades_to_one_row(self):
        """`Specialty.department` is PROTECT, so a bundle can carry a deletion this side
        physically cannot perform. It must be reported as one refused row, not raised —
        ProtectedError is an IntegrityError, and letting it escape would abort the batch
        and re-poison every future cycle with the identical bundle."""
        Specialty.objects.create(
            school=self.school, department=self.dept, name="Held", code="HLD-P"
        )
        out = apply_deletes(
            str(self.school.id), self.admin,
            [_delete_row("department", self.dept.pk, timezone.now())],
            sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 422)
        self.assertEqual(out["results"][0]["data"]["error"], "delete_failed")
        self.assertTrue(Department.objects.filter(pk=self.dept.pk).exists())

    def test_a_deletion_older_than_the_cursor_is_not_re_shipped(self):
        self.dept.delete()
        rows, meta = build_edge_delta_rows(self.school)
        self.assertTrue(any(r.get("op") == DELETE_OP for r in rows))

        again, _ = build_edge_delta_rows(self.school, since=meta["high_water"])
        self.assertEqual([r for r in again if r.get("op") == DELETE_OP], [])

    def test_the_wire_split_routes_a_delete_row_to_the_delete_path(self):
        """A deletion carrying an anchor must not be mistaken for an offline-created row —
        that would UPSERT the very row the far side just deleted."""
        rows = [
            _update_row("department", 1, {"name": "x"}, timezone.now()),
            _update_row("department", 2, {"name": "y"}, timezone.now(), client_offline_id="a1"),
            _delete_row("department", 3, timezone.now(), client_offline_id="a2"),
            "not-a-dict",
        ]
        updates, inserts, deletes, malformed = split_bundle_rows(rows)
        self.assertEqual(len(updates), 1)
        self.assertEqual(len(inserts), 1)
        self.assertEqual([r["id"] for r in deletes], ["3"])
        self.assertEqual(malformed, 1)


# --------------------------------------------------------------------------- #
# Policy: a delete is a write and answers to the same authority
# --------------------------------------------------------------------------- #
class DeletionAuthorityTests(_Fixture):
    def setUp(self):
        super().setUp()
        from apps.finance.models import Invoice

        self.Invoice = Invoice

    def _an_invoice(self):
        from decimal import Decimal

        from apps.finance.models import ComplianceProfile
        from apps.people.models import StudentProfile

        profile = ComplianceProfile.objects.create(name="CP del", country_code="CM")
        student = StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="L", student_code="S-DEL-1"
        )
        return self.Invoice.objects.create(
            school=self.school, profile=profile, student=student,
            total_amount=Decimal("100.00"), balance_amount=Decimal("100.00"),
        )

    def test_a_box_may_not_delete_a_money_record_on_the_cloud(self):
        inv = self._an_invoice()
        out = self._push([_delete_row("invoice", inv.pk, timezone.now())])

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["results"][0]["data"]["error"], "delete_refused_protected")
        self.assertTrue(self.Invoice.objects.filter(pk=inv.pk).exists())

    def test_a_refused_delete_re_asserts_the_row_so_the_sides_cannot_diverge(self):
        """The appliance has ALREADY deleted its copy. Without re-assertion the cloud's
        row is older than the box's pull cursor, so it is never offered again and the two
        sides stay permanently different with nothing reporting it."""
        inv = self._an_invoice()
        before = self.Invoice.objects.get(pk=inv.pk).updated_at

        out = self._push([_delete_row("invoice", inv.pk, timezone.now())])

        self.assertTrue(out["results"][0]["data"]["reasserted"])
        after = self.Invoice.objects.get(pk=inv.pk).updated_at
        self.assertGreater(after, before, "the row was not put back in the next pull window")

    def test_the_cloud_deleting_a_money_record_honours_the_model_soft_delete(self):
        """Direction is the whole point: money is cloud-authoritative, not undeletable.

        But `Invoice.delete()` is a SOFT delete — the platform keeps voided invoices for
        legal traceability. The rail must not overrule that: it calls the INSTANCE's
        delete(), so the row is voided rather than destroyed, and it must then NOT leave a
        tombstone behind, because a tombstone would refuse every later update to a row
        that still exists.
        """
        inv = self._cloud_authored("invoice", self._an_invoice())
        out = self._pull([_delete_row("invoice", inv.pk, timezone.now())])

        self.assertEqual(out["results"][0]["data"], {"deleted": False, "soft_deleted": True})
        inv.refresh_from_db()
        self.assertIsNotNone(inv.deleted_at)
        self.assertEqual(inv.status, self.Invoice.Status.VOID)
        self.assertFalse(
            SyncTombstone.objects.filter(entity_type="invoice", local_pk=str(inv.pk)).exists(),
            "a soft-deleted row still exists, so burying it would refuse its future updates",
        )

    def test_an_online_required_domain_is_never_deleted_through_the_rail(self):
        """No entity on the rail is ONLINE_REQUIRED today, so the branch is proven by
        DECLARING one that is registered. Keeping the guard is not speculative: the
        registry fails closed precisely so that a future registration inherits it, and a
        deletion is the one operation where discovering the gap later means data is
        already gone."""
        from unittest import mock

        from apps.sync_engine.policy_registry import (
            POLICIES, MergeStrategy, SyncPolicy,
        )

        locked = dict(POLICIES)
        locked["department"] = SyncPolicy(
            entity="department", strategy=MergeStrategy.ONLINE_REQUIRED, protected=True
        )
        with mock.patch.dict(
            "apps.sync_engine.policy_registry.POLICIES", locked, clear=True
        ):
            out = self._pull([_delete_row("department", self.dept.pk, timezone.now())])
        self.assertEqual(out["results"][0]["data"]["error"], "online_required")
        self.assertTrue(Department.objects.filter(pk=self.dept.pk).exists())

    def test_a_non_admin_principal_may_not_delete_anything(self):
        weak = User.objects.create_user(
            username="weak-del", password="x" * 12, role=User.Role.STUDENT
        )
        out = apply_deletes(
            str(self.school.id), weak, [_delete_row("department", self.dept.pk, timezone.now())],
            sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 403)
        self.assertTrue(Department.objects.filter(pk=self.dept.pk).exists())


# --------------------------------------------------------------------------- #
# Dominance: the same answer whichever side is asked first
# --------------------------------------------------------------------------- #
class DeleteDominanceTests(_Fixture):
    def test_an_edit_older_than_the_burial_does_not_resurrect_the_row(self):
        pk = self.dept.pk
        buried_at = timezone.now()
        self._pull([_delete_row("department", pk, buried_at)])

        out = apply_changes(
            str(self.school.id), self.admin,
            [_update_row("department", pk, {"name": "Zombie"}, buried_at - dt.timedelta(minutes=5))],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["data"]["error"], "deleted_upstream")
        self.assertFalse(Department.objects.filter(pk=pk).exists())

    def test_a_strictly_newer_write_DOES_resurrect_the_row(self):
        """A burial is not a permanent ban on a pk. The far side deliberately writing
        after the deletion is a resurrection, and it must win — otherwise a mistaken
        delete could never be undone across the boundary."""
        pk = self.dept.pk
        buried_at = timezone.now()
        self._pull([_delete_row("department", pk, buried_at)])

        out = apply_changes(
            str(self.school.id), self.admin,
            [_update_row("department", pk, {"name": "Reborn", "code": "RBN"},
                         buried_at + dt.timedelta(minutes=5))],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 201)
        self.assertEqual(Department.objects.get(pk=pk).name, "Reborn")
        self.assertFalse(
            SyncTombstone.objects.filter(entity_type="department", local_pk=str(pk)).exists(),
            "the stale tombstone would re-delete the resurrected row on the next cycle",
        )

    def test_dominance_is_order_independent(self):
        """Delete-then-edit and edit-then-delete must end in the SAME state. This is the
        acceptance criterion the whole design exists to satisfy."""
        edit_at = timezone.now()
        delete_at = edit_at + dt.timedelta(minutes=1)

        a = self._cloud_authored(
            "department",
            Department.objects.create(school=self.school, name="A", code="AAA"),
        )
        apply_changes(
            str(self.school.id), self.admin,
            [_update_row("department", a.pk, {"name": "Edited"}, edit_at)],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self._pull([_delete_row("department", a.pk, delete_at)])
        first_order_exists = Department.objects.filter(pk=a.pk).exists()

        b = self._cloud_authored(
            "department",
            Department.objects.create(school=self.school, name="B", code="BBB"),
        )
        self._pull([_delete_row("department", b.pk, delete_at)])
        apply_changes(
            str(self.school.id), self.admin,
            [_update_row("department", b.pk, {"name": "Edited"}, edit_at)],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        second_order_exists = Department.objects.filter(pk=b.pk).exists()

        self.assertEqual(first_order_exists, second_order_exists)
        self.assertFalse(first_order_exists, "the later deletion must dominate the earlier edit")

    def test_an_offline_created_row_is_not_re_inserted_after_it_was_deleted(self):
        """Matched by anchor, not pk — so without the anchor index the upsert would find
        nothing, insert afresh, and the far side would delete it again. Every cycle."""
        from datetime import date

        from apps.academics.models import AcademicYear

        year = AcademicYear.objects.create(
            school=self.school, name="2026/2027-del",
            start_date=date(2026, 9, 1), end_date=date(2027, 6, 30),
        )
        anchor = "coid-del-1"
        created = apply_edge_inserts(
            str(self.school.id), self.admin,
            [{
                "entity_type": "classroom", "id": 991, "client_offline_id": anchor,
                "changes": {
                    "name": "Offline Room", "academic_year_id": year.pk,
                    "department_id": self.dept.pk, "code": "OFF-ROOM-1",
                },
                "updated_at": timezone.now().isoformat(),
            }],
            sync_origin="edge-push",
        )
        self.assertEqual(created["created"], 1, created["results"])
        room_pk = created["results"][0]["data"]["id"]

        buried_at = timezone.now()
        self._pull([_delete_row("classroom", room_pk, buried_at, client_offline_id=anchor)])
        self.assertFalse(Classroom.objects.filter(pk=room_pk).exists())

        again = apply_edge_inserts(
            str(self.school.id), self.admin,
            [{
                "entity_type": "classroom", "id": 991, "client_offline_id": anchor,
                "changes": {
                    "name": "Offline Room", "academic_year_id": year.pk,
                    "department_id": self.dept.pk, "code": "OFF-ROOM-1",
                },
                "updated_at": (buried_at - dt.timedelta(minutes=1)).isoformat(),
            }],
            sync_origin="edge-push",
        )
        self.assertEqual(again["results"][0]["data"]["error"], "deleted_upstream")
        self.assertEqual(Classroom.objects.filter(client_offline_id=anchor).count(), 0)


# --------------------------------------------------------------------------- #
# Safety valves
# --------------------------------------------------------------------------- #
class DeletionSafetyTests(_Fixture):
    @override_settings(RMC_SYNC_MAX_DELETES_PER_BUNDLE=2)
    def test_a_flood_of_deletions_is_refused_WHOLE(self):
        """A mistaken bulk action on one side must cost a loud refusal, not a mirrored
        wipe. Refused whole on purpose: half a wipe plus an error is the worst outcome."""
        keep = [Department.objects.create(school=self.school, name=f"D{i}", code=f"D{i}")
                for i in range(3)]
        out = self._pull([_delete_row("department", d.pk, timezone.now()) for d in keep])

        self.assertEqual(out["deleted"], 0)
        self.assertEqual(out["results"][0]["data"]["error"], "delete_flood_guard")
        self.assertEqual(out["results"][0]["data"]["max_deletes"], 2)
        self.assertEqual(Department.objects.filter(pk__in=[d.pk for d in keep]).count(), 3)

    @override_settings(RMC_SYNC_DELETE_PROPAGATION_ENABLED=False)
    def test_the_kill_switch_restores_the_previous_behaviour_exactly(self):
        pk = self.dept.pk
        out = self._pull([_delete_row("department", pk, timezone.now())])
        self.assertEqual(out["results"][0]["data"]["error"], "delete_propagation_disabled")
        self.assertTrue(Department.objects.filter(pk=pk).exists())

        Department.objects.create(school=self.school, name="Gone", code="GON").delete()
        rows, _meta = build_edge_delta_rows(self.school)
        self.assertEqual([r for r in rows if r.get("op") == DELETE_OP], [])

    def test_tombstones_older_than_the_window_are_pruned(self):
        record_tombstone(
            self.school.id, "department", 4242,
            deleted_at=timezone.now() - dt.timedelta(days=400),
        )
        record_tombstone(self.school.id, "department", 4243, deleted_at=timezone.now())

        removed = prune_tombstones(self.school)
        self.assertEqual(removed, 1)
        self.assertEqual(
            list(SyncTombstone.objects.filter(school=self.school).values_list("local_pk", flat=True)),
            ["4243"],
        )

    def test_the_dominance_index_is_scoped_to_one_school(self):
        other = School.objects.create(name="Other", slug="other-t", subdomain="other-t")
        record_tombstone(other.id, "department", 77, deleted_at=timezone.now())
        record_tombstone(self.school.id, "department", 88, deleted_at=timezone.now())

        index = tombstone_index(self.school.id, ("department",))
        self.assertIn(("department", "88"), index)
        self.assertNotIn(("department", "77"), index)


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY="delete-e2e-key")
class DeletionEndToEndThroughTheWireTests(TestCase):
    """A-Z: a real signed bundle carrying a deletion, applied by the real inbox.

    Every other test here exercises one link. This one exercises the whole chain the
    appliance actually runs — tombstone -> delta row -> signed NDJSON -> HMAC verify ->
    replay guard -> row split -> apply_deletes — because that chain is where the pieces
    disagree, and a deletion that is correct at every stage and lost between two of them
    is exactly the failure this work exists to prevent.
    """

    def setUp(self):
        import uuid as _uuid

        uid = _uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Wire {uid}", slug=f"wire-{uid}", subdomain=f"wire{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"wire_{uid}", password="Test1234", email=f"w{uid}@t.com"
        )
        from apps.schools.models import SchoolMembership

        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.dept = Department.objects.create(
            school=self.school, name="Doomed", code=f"DOOM-{uid}"
        )

    def test_a_deletion_survives_the_signed_bundle_round_trip(self):
        from apps.sync_engine.delta_bundle import export_delta_bundle
        from apps.sync_engine.edge_inbox import apply_pulled_bundle

        pk = self.dept.pk
        self.dept.delete()

        rows, _meta = build_edge_delta_rows(self.school)
        data = export_delta_bundle(
            school_id=str(self.school.id), rows=rows, device_id="cloud"
        )

        # Re-create the row so the apply has something to remove — this stands in for the
        # far side, which still holds the record the sender has just buried.
        stand_in = Department.objects.create(
            school=self.school, id=pk, name="Doomed", code=self.dept.code
        )
        # ...and stand in COMPLETELY. A cloud-authored row is on the box because the
        # pull path put it there at the operator's pk, which records an apply-ledger
        # entry; that entry is what tells the delete path this pk means the same row on
        # both sides. Without it the row is indistinguishable from one created on the
        # box, which a far-side pk may not delete.
        record_sync_apply(
            str(self.school.id), "department", stand_in.pk,
            stand_in.updated_at, "cloud-pull",
        )

        result = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["deleted"], 1, result)
        self.assertFalse(Department.objects.filter(pk=pk).exists())

    def test_the_replay_guard_refuses_the_same_bundle_twice(self):
        """A bundle captured BEFORE a row was deleted resurrects it on replay. This is the
        chain where that matters, so the guard is asserted here rather than only in unit
        isolation."""
        from apps.sync_engine.delta_bundle import export_delta_bundle
        from apps.sync_engine.edge_inbox import apply_pulled_bundle

        self.dept.delete()
        rows, _meta = build_edge_delta_rows(self.school)
        data = export_delta_bundle(
            school_id=str(self.school.id), rows=rows, device_id="cloud"
        )

        first = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertTrue(first["ok"], first)

        second = apply_pulled_bundle(self.school, self.user, data, origin="cloud-pull")
        self.assertFalse(second["ok"])
        self.assertEqual(second["errors"], ["bundle_replayed"])
