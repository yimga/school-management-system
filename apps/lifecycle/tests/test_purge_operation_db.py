"""DB-backed integration tests for PurgeOperation (owner-decision b).

These exercise the parts of the purge tracking that ONLY exist at the database
layer and therefore cannot be proven by the no-DB SimpleTestCases:

- the partial UniqueConstraint ``uniq_active_purge_per_school`` is actually
  enforced by the DB (a mocked ``objects.create`` never hits it);
- ``begin_purge_operation`` recovers from a REAL IntegrityError race and reuses
  the winning row;
- ``complete_purge_operation`` persists a signed certificate + completed_phases
  that round-trip from the DB;
- ``revoke_all_sessions_for_school`` matches + deletes real django sessions by
  ``_auth_user_id`` (the string-vs-int handling that a prior bug got wrong).

What these deliberately do NOT cover (genuinely needs a live multi-tenant
Postgres, not the sqlite test DB): the destructive ``drop_tenant_schema_for_school``
+ ``delete_school_record_resilient`` themselves, and the offline token/device
revocation (those models carry a required School FK). Those remain
structurally-validated + audit-verified, not live-run here.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.lifecycle import purge_certificate as cert
from apps.lifecycle import purge_operations as ops
from apps.lifecycle.models_purge import PurgeOperation

STT = PurgeOperation.Status


class PurgeConstraintDBTests(TestCase):
    def test_partial_unique_constraint_blocks_second_active_op(self):
        PurgeOperation.objects.create(
            school_id="5", school_slug="s", status=STT.RUNNING
        )
        # A second non-terminal op (PENDING is also in the condition) for the
        # same school must be rejected by the DB.
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                PurgeOperation.objects.create(
                    school_id="5", school_slug="s", status=STT.PENDING
                )

    def test_constraint_allows_new_op_after_terminal(self):
        # The condition only covers pending/running, so a COMPLETED op must not
        # block a fresh RUNNING op for the same school (re-purge is allowed).
        PurgeOperation.objects.create(
            school_id="9", school_slug="s", status=STT.COMPLETED
        )
        op2 = PurgeOperation.objects.create(
            school_id="9", school_slug="s", status=STT.RUNNING
        )
        self.assertEqual(op2.status, STT.RUNNING)

    def test_normal_resume_reuses_row_and_preserves_phases(self):
        existing = PurgeOperation.objects.create(
            school_id="3",
            school_slug="s",
            status=STT.RUNNING,
            completed_phases=["sessions_revoked"],
        )
        op = ops.begin_purge_operation(school_id="3", school_slug="s")
        self.assertEqual(op.pk, existing.pk)
        self.assertIn("sessions_revoked", op.completed_phases)
        self.assertEqual(PurgeOperation.objects.filter(school_id="3").count(), 1)

    def test_complete_persists_verifiable_certificate_and_phases(self):
        op = ops.begin_purge_operation(school_id="77", school_slug="seventy-seven")
        ops.mark_purge_phase(op, "sessions_revoked")
        ops.mark_purge_phase(op, "records_deleted")
        ops.complete_purge_operation(
            op=op,
            row_total=42,
            schema_dropped=True,
            manifest_path="/var/x.json",
            sessions_revoked=3,
        )
        op.refresh_from_db()
        self.assertEqual(op.status, STT.COMPLETED)
        self.assertEqual(op.row_total, 42)
        self.assertTrue(op.schema_dropped)
        self.assertIn("sessions_revoked", op.completed_phases)
        self.assertIn("records_deleted", op.completed_phases)
        # The signed certificate round-trips from the persisted row.
        self.assertTrue(op.certificate_signature)
        self.assertTrue(
            cert.verify_deletion_certificate(op.certificate, op.certificate_signature)
        )

    def test_tampered_persisted_certificate_fails_verify(self):
        op = ops.begin_purge_operation(school_id="78", school_slug="s")
        ops.complete_purge_operation(op=op, row_total=1)
        op.refresh_from_db()
        tampered = dict(op.certificate)
        tampered["row_total"] = 9999
        self.assertFalse(
            cert.verify_deletion_certificate(tampered, op.certificate_signature)
        )


class PurgeRaceDBTests(TransactionTestCase):
    """The IntegrityError-recovery branch needs real autocommit semantics."""

    def test_begin_recovers_from_real_integrity_race(self):
        winner = PurgeOperation.objects.create(
            school_id="8", school_slug="s", status=STT.RUNNING
        )
        # Simulate the race window: find_resumable misses on the first check
        # (so begin tries to create), then the create hits the REAL DB
        # constraint, and the retry find_resumable returns the winner.
        with mock.patch.object(ops, "find_resumable", side_effect=[None, winner]):
            op = ops.begin_purge_operation(school_id="8", school_slug="s")
        self.assertEqual(op.pk, winner.pk)
        self.assertEqual(PurgeOperation.objects.filter(school_id="8").count(), 1)


class SessionRevocationDBTests(TestCase):
    @staticmethod
    def _make_session(uid) -> str:
        store = SessionStore()
        store["_auth_user_id"] = str(uid)
        store.create()
        return store.session_key

    def test_revoke_deletes_only_member_sessions(self):
        member_key = self._make_session(101)
        other_key = self._make_session(102)
        revoked = ops.revoke_all_sessions_for_school(
            school_id="1", user_ids=[101]
        )
        self.assertEqual(revoked, 1)
        self.assertFalse(Session.objects.filter(session_key=member_key).exists())
        self.assertTrue(Session.objects.filter(session_key=other_key).exists())

    def test_revoke_skips_expired_sessions(self):
        member_key = self._make_session(201)
        Session.objects.filter(session_key=member_key).update(
            expire_date=timezone.now() - timezone.timedelta(days=1)
        )
        revoked = ops.revoke_all_sessions_for_school(
            school_id="1", user_ids=[201]
        )
        # Expired sessions are out of scope (already dead); not counted.
        self.assertEqual(revoked, 0)

    def test_revoke_noop_for_empty_user_set(self):
        key = self._make_session(301)
        revoked = ops.revoke_all_sessions_for_school(school_id="1", user_ids=[])
        self.assertEqual(revoked, 0)
        self.assertTrue(Session.objects.filter(session_key=key).exists())
