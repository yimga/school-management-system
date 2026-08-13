"""Fresh adversarial-review fixes for the bidirectional edge-sync build (round 2).

Each test pins one review finding and is written to FAIL before its fix:

  F1 (HIGH)  — apply_changes had no per-row savepoint: one un-appliable UPDATE rolled back
               the whole batch and 500'd the receiver, permanently wedging the outbox.
  F2 (MED)   — Sync Center "keep client version" silently no-op'd for derived entities
               (resolver rebuilt config without include_derived=True).
  F3 (MED)   — Department.code was globally unique, so a box department whose code exists
               for ANOTHER tenant could not sync up on a shared cloud. Now per-(school,code).
  F4 (MED)   — academic_year.is_locked / enable_gce_registration (year-end lock, exam gate)
               were two-way LWW, so a stale box edit could reopen a cloud-locked year.
  F5 (LOW)   — a delta row missing updated_at unconditionally won; now it's a conflict.
  F6 (LOW)   — echo-suppression stalled the cursor: high_water skipped suppressed rows.
  F8 (LOW)   — apply_edge_inserts wrote a verbatim FK without checking it belongs to school.
"""
from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import AcademicYear, Department
from apps.accounts.models import User
from apps.api.sync_services import (
    _conflict_decision,
    _get_entity_config,
    apply_changes,
    apply_edge_inserts,
)
from apps.people.models import StudentNote, StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY="edge-sync-review2-key")
class EdgeSyncReview2Tests(TestCase):
    def setUp(self):
        self.uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"R2 {self.uid}", slug=f"r2-{self.uid}", subdomain=f"r2{self.uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"r2_admin_{self.uid}", password="Test1234", email=f"r2{self.uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.future = (timezone.now() + timezone.timedelta(minutes=10)).isoformat()

    def _other_school(self, tag="oth"):
        u = uuid.uuid4().hex[:6]
        return School.objects.create(
            name=f"{tag} {u}", slug=f"{tag}-{u}", subdomain=f"{tag}{u}", is_active=True
        )

    # ------------------------------------------------------------------ F1
    def test_f1_one_unappliable_update_does_not_roll_back_the_batch(self):
        s1 = StudentProfile.objects.create(
            school=self.school, first_name="Keep", last_name="Me", date_of_birth="2012-01-01"
        )
        s2 = StudentProfile.objects.create(
            school=self.school, first_name="Also", last_name="Here", date_of_birth="2012-02-02"
        )
        # s2's row violates NOT NULL (first_name=None) -> a DB error on save. Before the
        # per-row savepoint this rolled back the WHOLE batch (s1 too) and RAISED (HTTP 500
        # at the receiver -> the outbox re-sends the poison bundle forever).
        out = apply_changes(
            str(self.school.id), self.user,
            [
                {"entity_type": "student", "id": s1.pk,
                 "changes": {"first_name": "Applied"}, "updated_at": self.future},
                {"entity_type": "student", "id": s2.pk,
                 "changes": {"first_name": None}, "updated_at": self.future},
            ],
            persist_conflicts=True, sync_origin="edge-push",
        )
        self.assertEqual(out["success_count"], 1, out)
        self.assertEqual(sorted(r["status"] for r in out["results"]), [200, 422], out)
        s1.refresh_from_db(); s2.refresh_from_db()
        self.assertEqual(s1.first_name, "Applied")   # good row NOT rolled back by its sibling
        self.assertEqual(s2.first_name, "Also")        # bad row unchanged

    # ------------------------------------------------------------------ F2
    def test_f2_sync_center_keep_client_applies_for_a_derived_entity(self):
        from apps.siteconfig.models import SyncConflict
        from apps.siteconfig.views_sync_center import _resolve_sync_conflict

        year = AcademicYear.objects.create(
            school=self.school, name="2024/2025", start_date="2024-09-01", end_date="2025-06-30"
        )
        conflict = SyncConflict.objects.create(
            school=self.school, entity_type="academic_year", entity_id=year.pk,
            client_data={"name": "2024/2025 (client)"}, server_data={"name": "2024/2025"},
            status=SyncConflict.Status.PENDING, reported_by=self.user,
        )
        _resolve_sync_conflict(conflict, SyncConflict.Status.RESOLVED_CLIENT, self.user)
        year.refresh_from_db(); conflict.refresh_from_db()
        # Before the fix the resolver rebuilt config WITHOUT the derived registry, so this
        # write was silently skipped while the record was still stamped RESOLVED_CLIENT.
        self.assertEqual(year.name, "2024/2025 (client)")
        self.assertEqual(conflict.status, SyncConflict.Status.RESOLVED_CLIENT)

    # ------------------------------------------------------------------ F3
    def test_f3_department_code_is_unique_per_school_not_globally(self):
        other = self._other_school("f3")
        Department.objects.create(school=other, name="Science", code="SCI")
        # Same code, different school -> now allowed (was a global-unique IntegrityError).
        Department.objects.create(school=self.school, name="Science", code="SCI")
        self.assertTrue(Department.objects.filter(school=self.school, code="SCI").exists())
        self.assertTrue(Department.objects.filter(school=other, code="SCI").exists())
        # Still unique WITHIN a school.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Department.objects.create(school=self.school, name="Dup", code="SCI")

    def test_f3_edge_insert_of_cross_tenant_colliding_code_now_succeeds(self):
        other = self._other_school("f3b")
        Department.objects.create(school=other, name="Arts", code="ART")
        out = apply_edge_inserts(
            str(self.school.id), self.user,
            [{"entity_type": "department", "id": 4242, "client_offline_id": "box-art",
              "changes": {"name": "Arts", "code": "ART"}, "updated_at": self.future}],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 1, out)  # was 422 insert_failed under global unique
        self.assertTrue(
            Department.objects.filter(school=self.school, client_offline_id="box-art", code="ART").exists()
        )

    # ------------------------------------------------------------------ F4
    def test_f4_academic_year_governance_flags_are_not_syncable(self):
        fields = _get_entity_config(include_derived=True)["academic_year"][1]
        self.assertNotIn("is_locked", fields)
        self.assertNotIn("enable_gce_registration", fields)
        self.assertIn("name", fields)        # benign master-data still syncs
        self.assertIn("is_active", fields)
        # Behaviorally: a box push cannot flip the lock, but a benign field still applies.
        year = AcademicYear.objects.create(
            school=self.school, name="Y", start_date="2024-09-01", end_date="2025-06-30",
            is_locked=True,
        )
        out = apply_changes(
            str(self.school.id), self.user,
            [{"entity_type": "academic_year", "id": year.pk,
              "changes": {"is_locked": False, "is_active": True}, "updated_at": self.future}],
            persist_conflicts=True, sync_origin="edge-push",
        )
        self.assertEqual(out["success_count"], 1, out)
        year.refresh_from_db()
        self.assertTrue(year.is_locked)   # the box could NOT reopen the cloud-locked year
        self.assertTrue(year.is_active)   # the benign field DID sync

    # ------------------------------------------------------------------ F5
    def test_f5_missing_client_timestamp_is_a_conflict_not_a_silent_overwrite(self):
        now = timezone.now()
        # Client omitted updated_at but the server row HAS one -> can't prove newer -> conflict.
        self.assertEqual(_conflict_decision("student", "edge-push", None, now), "conflict")
        self.assertEqual(_conflict_decision("student", None, None, now), "conflict")
        # Brand-new (nothing on the server to beat) still applies.
        self.assertEqual(_conflict_decision("student", None, None, None), "apply")

    # ------------------------------------------------------------------ F6
    def test_f6_high_water_advances_past_a_suppressed_echo(self):
        dept = Department.objects.create(
            school=self.school, name="Sci", code=f"S{self.uid[:4]}"
        )
        # Written AS SYNC (cloud-pull) -> recorded in the echo ledger -> the reverse delta
        # will suppress it. It is also the newest (only) row in the window.
        apply_changes(
            str(self.school.id), self.user,
            [{"entity_type": "department", "id": dept.pk,
              "changes": {"name": "Applied Sci"}, "updated_at": self.future}],
            persist_conflicts=True, sync_origin="cloud-pull",
        )
        data, meta = build_edge_delta_bundle(self.school, since=None, entities=["department"])
        rows, errs = verify_and_parse_bundle(data, expected_school_id=self.school.id)
        self.assertFalse(errs, errs)
        self.assertEqual([r for r in rows if r["id"] == dept.pk], [], "echo should be suppressed")
        # The cursor still moved past the suppressed row. Before the fix high_water was None
        # (the row was skipped before high_water updated), so the cursor never advanced and
        # every cycle re-scanned/re-suppressed the same window.
        self.assertIsNotNone(meta["high_water_iso"])

    # ------------------------------------------------------------------ F8
    def test_f8_edge_insert_drops_a_cross_tenant_fk(self):
        other = self._other_school("f8")
        foreign = StudentProfile.objects.create(
            school=other, first_name="For", last_name="Eign", date_of_birth="2012-01-01"
        )
        out = apply_edge_inserts(
            str(self.school.id), self.user,
            [{"entity_type": "student_note", "id": 9001, "client_offline_id": "note-x",
              "changes": {"student_id": foreign.pk, "body": "hi", "kind": "note"},
              "updated_at": self.future}],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 1, out)
        note = StudentNote.objects.get(school=self.school, client_offline_id="note-x")
        self.assertIsNone(note.student_id)  # cross-tenant referent dropped, never linked
        self.assertIn("student_id", out["results"][0]["data"].get("dropped_fks", []))

    def test_f8_edge_insert_keeps_a_same_school_fk(self):
        ours = StudentProfile.objects.create(
            school=self.school, first_name="Our", last_name="Kid", date_of_birth="2012-01-01"
        )
        out = apply_edge_inserts(
            str(self.school.id), self.user,
            [{"entity_type": "student_note", "id": 9002, "client_offline_id": "note-y",
              "changes": {"student_id": ours.pk, "body": "hey", "kind": "note"},
              "updated_at": self.future}],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 1, out)
        note = StudentNote.objects.get(school=self.school, client_offline_id="note-y")
        self.assertEqual(note.student_id, ours.pk)  # in-school referent preserved
