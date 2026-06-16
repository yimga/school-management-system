"""Remote Support P2 — service-layer lifecycle, guards, audit, notify (no DB)."""

from __future__ import annotations

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase

from apps.platform_runtime import remote_support_service as svc
from apps.platform_runtime.models_remote_support import RemoteSupportSession

S = RemoteSupportSession.Status


class _School:
    pk = 1
    id = 1
    settings: dict = {}


def _session(**kw):
    s = RemoteSupportSession(school_id=1, **kw)
    # Pre-seed the FK cache so `session.school` resolves to a stub without a DB
    # query (these are no-DB SimpleTestCases; the gate is mocked anyway).
    s._state.fields_cache["school"] = _School()
    return s


@mock.patch.object(RemoteSupportSession, "record_lifecycle_audit")
@mock.patch.object(RemoteSupportSession, "save")
class RemoteSupportServiceTests(SimpleTestCase):
    def test_request_creates_requested_session(self, save, audit):
        with mock.patch.object(RemoteSupportSession.objects, "create") as create:
            create.return_value = _session(status=S.REQUESTED)
            svc.request_remote_support(
                school=_School(), requested_by=None, reason="help"
            )
        self.assertTrue(create.called)
        self.assertEqual(create.call_args.kwargs["status"], S.REQUESTED)

    def test_accept_denied_without_authorization(self, save, audit):
        s = _session(status=S.REQUESTED)
        with mock.patch.object(
            svc, "operator_can_remote_support", return_value=False
        ):
            with self.assertRaises(PermissionDenied):
                svc.accept_remote_support(session=s, operator=None)
        self.assertFalse(save.called)

    def test_accept_transitions_and_notifies(self, save, audit):
        s = _session(status=S.REQUESTED)
        with mock.patch.object(
            svc, "operator_can_remote_support", return_value=True
        ), mock.patch.object(svc, "_notify_tenant_user") as notify:
            svc.accept_remote_support(session=s, operator=None)
        self.assertEqual(s.status, S.ACCEPTED)
        self.assertTrue(save.called)
        self.assertTrue(notify.called)

    def test_accept_denied_when_session_already_closed(self, save, audit):
        s = _session(status=S.ENDED)
        with mock.patch.object(
            svc, "operator_can_remote_support", return_value=True
        ):
            with self.assertRaises(PermissionDenied):
                svc.accept_remote_support(session=s, operator=None)

    def test_activate_requires_consent(self, save, audit):
        s = _session(status=S.ACCEPTED, requires_consent=True)
        with mock.patch.object(
            svc, "operator_can_remote_support", return_value=True
        ):
            with self.assertRaises(PermissionDenied):
                svc.activate_remote_support(session=s, operator=None)

    def test_activate_succeeds_with_consent(self, save, audit):
        s = _session(status=S.ACCEPTED, requires_consent=False)
        with mock.patch.object(
            svc, "operator_can_remote_support", return_value=True
        ):
            svc.activate_remote_support(session=s, operator=None)
        self.assertEqual(s.status, S.ACTIVE)

    def test_record_consent_stamps_consent(self, save, audit):
        s = _session(status=S.ACCEPTED, requires_consent=True)
        svc.record_consent(session=s, by_user=None)
        self.assertTrue(s.consent_satisfied)
        self.assertTrue(save.called)

    def test_consent_promotes_accepted_to_active(self, save, audit):
        # The online handshake closes here: consent on an ACCEPTED session goes
        # ACTIVE (no separate operator "begin" click is needed).
        s = _session(status=S.ACCEPTED, requires_consent=True)
        svc.record_consent(session=s, by_user=None)
        self.assertEqual(s.status, S.ACTIVE)

    def test_consent_does_not_activate_when_not_accepted(self, save, audit):
        # Consent recorded before an operator accepts must not jump to ACTIVE.
        s = _session(status=S.REQUESTED, requires_consent=True)
        svc.record_consent(session=s, by_user=None)
        self.assertEqual(s.status, S.REQUESTED)

    def test_accept_auto_activates_when_consent_not_required(self, save, audit):
        s = _session(status=S.REQUESTED, requires_consent=False)
        with mock.patch.object(
            svc, "operator_can_remote_support", return_value=True
        ), mock.patch.object(svc, "_notify_tenant_user"):
            svc.accept_remote_support(session=s, operator=None)
        self.assertEqual(s.status, S.ACTIVE)

    def test_end_sets_summary_and_notifies(self, save, audit):
        s = _session(status=S.ACTIVE)
        with mock.patch.object(svc, "_notify_tenant_user") as notify:
            svc.end_remote_support(
                session=s, actor=None, reason="resolved", summary="done"
            )
        self.assertEqual(s.status, S.ENDED)
        self.assertEqual(s.summary, "done")
        self.assertFalse(s.is_open)
        self.assertTrue(notify.called)

    def test_decline_closes_session(self, save, audit):
        s = _session(status=S.REQUESTED)
        svc.decline_remote_support(session=s, actor=None)
        self.assertEqual(s.status, S.DECLINED)
        self.assertFalse(s.is_open)

    def test_cancel_closes_session(self, save, audit):
        s = _session(status=S.REQUESTED)
        svc.cancel_remote_support(session=s, actor=None)
        self.assertEqual(s.status, S.CANCELLED)
        self.assertFalse(s.is_open)
