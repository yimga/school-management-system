"""Phase 3 slice 1 — the generalized sync registry covers CLASS-A master data beyond
the original three entities, both directions.

Proves that `applicant` and `student_note` (each already carrying a client_offline_id
anchor + auto_now updated_at, so ZERO schema change) now:
  * update by pk through apply_changes,
  * insert by (school, client_offline_id) through apply_edge_inserts, with a
    new-references-new FK (student_note.student_id) remapped onto the referent's operator
    pk via the PER-ENTITY fk-target derivation, and
  * respect echo-suppression like the built-in entities.

Also guards the invariant that the original three entities' curated field sets are
unchanged by the generalized registry.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import User
from apps.api.sync_services import (
    _get_entity_config,
    apply_changes,
    apply_edge_inserts,
)
from apps.people.models import Applicant, StudentNote, StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.delta_bundle import verify_and_parse_bundle
from apps.sync_engine.edge_outbox import build_edge_delta_bundle

_SIGN_KEY = "registry-expansion-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class SyncRegistryExpansionTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Reg {uid}", slug=f"reg-{uid}", subdomain=f"reg{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"reg_admin_{uid}", password="Test1234", email=f"r{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.future = (timezone.now() + timezone.timedelta(minutes=10)).isoformat()

    def test_registry_lists_new_class_a_entities_without_changing_the_originals(self):
        # Online (non-edge) callers only ever get the original three.
        self.assertEqual(set(_get_entity_config()), {"student", "attendance", "classroom"})
        # Edge sync operations get the expanded set.
        cfg = _get_entity_config(include_derived=True)
        self.assertIn("applicant", cfg)
        self.assertIn("student_note", cfg)
        # teacher is intentionally DEFERRED (compensation fields need Phase-4 policy).
        self.assertNotIn("teacher", cfg)
        # Original curated field sets must be untouched by the generalized registry.
        self.assertEqual(cfg["classroom"][1], {"name", "academic_year_id"})
        self.assertEqual(
            cfg["attendance"][1], {"student_id", "classroom_id", "date", "status", "remarks"}
        )
        # A new entity's derived set carries data fields but NEVER the anchor / scope /
        # timestamps / a shared-model (User) FK.
        note_fields = cfg["student_note"][1]
        self.assertIn("body", note_fields)
        self.assertIn("student_id", note_fields)
        self.assertFalse(
            note_fields & {"id", "school", "client_offline_id", "updated_at", "created_at", "author_id"}
        )

    def test_student_note_updates_by_pk(self):
        note = StudentNote.objects.create(school=self.school, body="Original", kind="note")
        out = apply_changes(
            str(self.school.id),
            self.user,
            [{"entity_type": "student_note", "id": note.pk,
              "changes": {"body": "Revised", "title": "Seen"}, "updated_at": self.future}],
            persist_conflicts=True, sync_origin="edge-push",
        )
        self.assertEqual(out["success_count"], 1, out)
        note.refresh_from_db()
        self.assertEqual(note.body, "Revised")
        self.assertEqual(note.title, "Seen")

    def test_applicant_updates_by_pk(self):
        app = Applicant.objects.create(
            school=self.school, first_name="Ada", last_name="N", email="ada@x.test"
        )
        out = apply_changes(
            str(self.school.id),
            self.user,
            [{"entity_type": "applicant", "id": app.pk,
              "changes": {"stage": "interview", "lead_source": "web"}, "updated_at": self.future}],
            persist_conflicts=True, sync_origin="edge-push",
        )
        self.assertEqual(out["success_count"], 1, out)
        app.refresh_from_db()
        self.assertEqual(app.stage, "interview")
        self.assertEqual(app.lead_source, "web")

    def test_new_student_note_references_new_student_is_remapped(self):
        # Both created offline in the SAME bundle; the note's student_id points at the
        # student's BOX-LOCAL pk and must be remapped onto the operator pk.
        local_student_pk = 717171
        rows = [
            {"entity_type": "student", "id": local_student_pk, "client_offline_id": "box-stu-n",
             "changes": {"first_name": "Noted", "last_name": "Kid"}, "updated_at": self.future},
            {"entity_type": "student_note", "id": 727272, "client_offline_id": "box-note-n",
             "changes": {"student_id": local_student_pk, "body": "Sticky", "kind": "note"},
             "updated_at": self.future},
        ]
        out = apply_edge_inserts(str(self.school.id), self.user, rows, sync_origin="edge-push")
        self.assertEqual(out["created"], 2, out)
        new_student = StudentProfile.objects.get(school=self.school, client_offline_id="box-stu-n")
        note = StudentNote.objects.get(school=self.school, client_offline_id="box-note-n")
        self.assertEqual(note.student_id, new_student.pk)          # remapped to operator pk
        self.assertNotEqual(note.student_id, local_student_pk)      # NOT the box local pk

    def test_edge_insert_update_bumps_updated_at_for_delta_visibility(self):
        # An offline-created row re-synced with a change must bump updated_at, or the
        # incremental delta cursor (filter(updated_at__gt=since)) never sees the edit.
        apply_edge_inserts(
            str(self.school.id), self.user,
            [{"entity_type": "student_note", "id": 111, "client_offline_id": "note-u",
              "changes": {"body": "first"}, "updated_at": self.future}],
            sync_origin="edge-push",
        )
        note = StudentNote.objects.get(school=self.school, client_offline_id="note-u")
        old = timezone.now() - timezone.timedelta(days=1)
        StudentNote.objects.filter(pk=note.pk).update(updated_at=old)  # bypasses auto_now
        out = apply_edge_inserts(
            str(self.school.id), self.user,
            [{"entity_type": "student_note", "id": 111, "client_offline_id": "note-u",
              "changes": {"body": "second"}, "updated_at": self.future}],
            sync_origin="edge-push",
        )
        self.assertEqual(out["updated"], 1, out)
        note.refresh_from_db()
        self.assertEqual(note.body, "second")
        self.assertGreater(note.updated_at, old)  # bumped -> delta cursor will pick it up

    def test_echo_suppression_applies_to_new_entities(self):
        note = StudentNote.objects.create(school=self.school, body="Base", kind="note")
        # Written AS SYNC -> ledger recorded -> must not be echoed by the reverse delta.
        apply_changes(
            str(self.school.id),
            self.user,
            [{"entity_type": "student_note", "id": note.pk,
              "changes": {"body": "FromCloud"}, "updated_at": self.future}],
            persist_conflicts=True,
            sync_origin="cloud-pull",
        )
        data, _m = build_edge_delta_bundle(self.school, since=None, entities=["student_note"])
        rows, errs = verify_and_parse_bundle(data, expected_school_id=self.school.id)
        self.assertFalse(errs, errs)
        self.assertEqual([r for r in rows if r["id"] == note.pk], [], "echoed a synced note")

        # Genuine local edit -> propagates.
        note.refresh_from_db()
        note.body = "LocalEdit"
        note.save(update_fields=["body", "updated_at"])
        data2, _m2 = build_edge_delta_bundle(self.school, since=None, entities=["student_note"])
        rows2, _e2 = verify_and_parse_bundle(data2, expected_school_id=self.school.id)
        shipped = [r for r in rows2 if r["id"] == note.pk]
        self.assertEqual(len(shipped), 1, "local edit to a new entity was suppressed")
        self.assertEqual(shipped[0]["changes"].get("body"), "LocalEdit")
