"""Operator (/super/) remote-support endpoints — gating smoke tests (no DB)."""

from __future__ import annotations

from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.schools import super_views_remote_support as srs
from apps.platform_runtime.models_remote_support import RemoteSupportSession

rf = RequestFactory()


class _U:
    is_authenticated = True
    is_superuser = False
    id = 7
    pk = 7


def _session_stub():
    return mock.Mock(
        id="11111111-1111-1111-1111-111111111111",
        school=object(),
        school_id=1,
    )


class SuperRemoteSupportTests(SimpleTestCase):
    def test_accept_denies_unauthorized_with_403(self):
        req = rf.post("/super/remote-support/x/accept/")
        req.user = _U()
        with mock.patch.object(
            srs, "get_object_or_404", return_value=_session_stub()
        ), mock.patch.object(
            srs, "operator_can_remote_support", return_value=False
        ):
            resp = srs.super_remote_support_accept(req, session_id="x")
        self.assertEqual(resp.status_code, 403)

    def test_accept_authorized_calls_service(self):
        req = rf.post("/super/remote-support/x/accept/")
        req.user = _U()
        with mock.patch.object(
            srs, "get_object_or_404", return_value=_session_stub()
        ), mock.patch.object(
            srs, "operator_can_remote_support", return_value=True
        ), mock.patch.object(srs.svc, "accept_remote_support") as accept:
            resp = srs.super_remote_support_accept(req, session_id="x")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(accept.called)

    def test_end_authorized_calls_service(self):
        req = rf.post("/super/remote-support/x/end/", {"summary": "done"})
        req.user = _U()
        with mock.patch.object(
            srs, "get_object_or_404", return_value=_session_stub()
        ), mock.patch.object(
            srs, "operator_can_remote_support", return_value=True
        ), mock.patch.object(srs.svc, "end_remote_support") as end:
            resp = srs.super_remote_support_end(req, session_id="x")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(end.called)

    def test_sessions_list_serializes(self):
        req = rf.get("/super/remote-support/sessions.json")
        req.user = _U()
        stub = RemoteSupportSession(status=RemoteSupportSession.Status.REQUESTED)
        qs = mock.Mock()
        qs.order_by.return_value = [stub]
        with mock.patch.object(
            RemoteSupportSession.objects, "filter", return_value=qs
        ):
            resp = srs.super_remote_support_sessions(req)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"sessions", resp.content)
