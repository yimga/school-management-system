"""Offboarding (owner-decision b): PurgeOperation + signed cert + revocation."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.lifecycle import purge_certificate as cert
from apps.lifecycle import purge_operations as ops
from apps.lifecycle.models_purge import PurgeOperation

STT = PurgeOperation.Status


class DeletionCertificateTests(SimpleTestCase):
    def test_sign_verify_roundtrip(self):
        payload = {"school_id": "1", "row_total": 10}
        sig = cert.sign_deletion_certificate(payload)
        self.assertEqual(len(sig), 128)  # hex SHA-512
        self.assertTrue(cert.verify_deletion_certificate(payload, sig))

    def test_tampered_payload_fails(self):
        payload = {"school_id": "1", "row_total": 10}
        sig = cert.sign_deletion_certificate(payload)
        self.assertFalse(
            cert.verify_deletion_certificate({"school_id": "1", "row_total": 11}, sig)
        )

    def test_empty_signature_fails(self):
        self.assertFalse(cert.verify_deletion_certificate({"a": 1}, ""))


class PurgeOperationModelTests(SimpleTestCase):
    def test_needs_resume_for_nonterminal(self):
        self.assertTrue(PurgeOperation(status=STT.RUNNING).needs_resume)
        self.assertTrue(PurgeOperation(status=STT.PENDING).needs_resume)
        self.assertFalse(PurgeOperation(status=STT.COMPLETED).needs_resume)
        self.assertFalse(PurgeOperation(status=STT.FAILED).needs_resume)

    def test_add_phase_idempotent(self):
        op = PurgeOperation()
        op.add_phase("rows")
        op.add_phase("rows")
        op.add_phase("schema")
        self.assertEqual(op.completed_phases, ["rows", "schema"])
        self.assertTrue(op.has_phase("rows"))
        self.assertFalse(op.has_phase("media"))

    def test_mark_completed_sets_timestamp(self):
        op = PurgeOperation()
        op.mark_completed()
        self.assertEqual(op.status, STT.COMPLETED)
        self.assertIsNotNone(op.completed_at)


@mock.patch.object(ops, "_audit")
class OrchestrationTests(SimpleTestCase):
    @mock.patch.object(PurgeOperation, "save")
    def test_begin_creates_when_none_resumable(self, save, audit):
        with mock.patch.object(
            ops, "find_resumable", return_value=None
        ), mock.patch.object(
            PurgeOperation.objects,
            "create",
            return_value=PurgeOperation(school_id="1", school_slug="s"),
        ) as create:
            ops.begin_purge_operation(school_id=1, school_slug="s")
        self.assertTrue(create.called)
        self.assertEqual(create.call_args.kwargs["status"], STT.RUNNING)

    @mock.patch.object(PurgeOperation, "save")
    def test_begin_resumes_existing(self, save, audit):
        existing = PurgeOperation(
            school_id="1", school_slug="s", status=STT.RUNNING
        )
        with mock.patch.object(ops, "find_resumable", return_value=existing):
            op = ops.begin_purge_operation(school_id=1, school_slug="s")
        self.assertIs(op, existing)
        self.assertTrue(save.called)

    @mock.patch.object(PurgeOperation, "save")
    def test_begin_reuses_winner_on_integrity_race(self, save, audit):
        # The partial-unique constraint rejects a second concurrent op for one
        # school; the loser must catch IntegrityError and reuse the winner's row
        # rather than raise or mint a duplicate certificate.
        from django.db import IntegrityError

        winner = PurgeOperation(
            school_id="1", school_slug="s", status=STT.RUNNING
        )
        # find_resumable: None on first check (race window), winner on retry.
        with mock.patch.object(
            ops, "find_resumable", side_effect=[None, winner]
        ), mock.patch.object(
            PurgeOperation.objects, "create", side_effect=IntegrityError("dup")
        ):
            op = ops.begin_purge_operation(school_id=1, school_slug="s")
        self.assertIs(op, winner)

    @mock.patch.object(PurgeOperation, "save")
    def test_complete_signs_verifiable_certificate(self, save, audit):
        op = PurgeOperation(school_id="1", school_slug="s")
        ops.complete_purge_operation(
            op=op, row_total=10, schema_dropped=True, sessions_revoked=3
        )
        self.assertEqual(op.status, STT.COMPLETED)
        self.assertTrue(op.certificate_signature)
        self.assertTrue(
            cert.verify_deletion_certificate(
                op.certificate, op.certificate_signature
            )
        )
        self.assertEqual(op.certificate["row_total"], 10)
        self.assertEqual(op.certificate["sessions_revoked"], 3)

    @mock.patch.object(PurgeOperation, "save")
    def test_fail_records_error(self, save, audit):
        op = PurgeOperation(school_id="1", school_slug="s")
        ops.fail_purge_operation(op, "schema drop boom")
        self.assertEqual(op.status, STT.FAILED)
        self.assertIn("boom", op.last_error)


class SessionRevocationTests(SimpleTestCase):
    def test_revokes_matching_sessions(self):
        from django.contrib.sessions.models import Session

        fake = mock.Mock()
        fake.get_decoded.return_value = {"_auth_user_id": "7"}
        with mock.patch.object(Session.objects, "filter", return_value=[fake]):
            n = ops.revoke_all_sessions_for_school(school_id="1", user_ids=[7])
        self.assertEqual(n, 1)
        self.assertTrue(fake.delete.called)

    def test_non_matching_session_kept(self):
        from django.contrib.sessions.models import Session

        fake = mock.Mock()
        fake.get_decoded.return_value = {"_auth_user_id": "999"}
        with mock.patch.object(Session.objects, "filter", return_value=[fake]):
            n = ops.revoke_all_sessions_for_school(school_id="1", user_ids=[7])
        self.assertEqual(n, 0)
        self.assertFalse(fake.delete.called)

    def test_no_users_returns_zero(self):
        self.assertEqual(
            ops.revoke_all_sessions_for_school(school_id="1", user_ids=[]), 0
        )
