"""Remote Support P2 — view smoke tests (no DB): gating + URL wiring."""

from __future__ import annotations

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.platform_runtime import views_remote_support as views

rf = RequestFactory()


class _U:
    is_authenticated = True
    is_superuser = False
    id = 7
    pk = 7


def _session_stub(**kw):
    base = dict(
        id="11111111-1111-1111-1111-111111111111",
        status="requested",
        channel="online",
        consent_satisfied=False,
        is_open=True,
        school=object(),
        school_id=1,
        requested_by_id=7,
    )
    base.update(kw)
    return mock.Mock(**base)


class RemoteSupportUrlWiringTests(SimpleTestCase):
    _UC = "config.tenant_urls"

    def test_routes_reverse(self):
        sid = "11111111-1111-1111-1111-111111111111"
        self.assertTrue(
            reverse("platform_runtime:remote_support_request", urlconf=self._UC)
        )
        self.assertTrue(
            reverse(
                "platform_runtime:remote_support_consent",
                args=[sid],
                urlconf=self._UC,
            )
        )
        self.assertTrue(
            reverse(
                "platform_runtime:remote_support_accept",
                args=[sid],
                urlconf=self._UC,
            )
        )
        self.assertTrue(
            reverse(
                "platform_runtime:remote_support_end", args=[sid], urlconf=self._UC
            )
        )


class RemoteSupportViewGateTests(SimpleTestCase):
    def test_request_help_requires_tenant_context(self):
        req = rf.post("/x/remote-support/request/")
        req.user = _U()
        resp = views.request_help(req)
        self.assertEqual(resp.status_code, 400)

    def test_request_help_creates_and_returns_201(self):
        req = rf.post("/x/remote-support/request/", {"reason": "help"})
        req.user = _U()
        req.school = mock.Mock(id=1)
        with mock.patch.object(
            views.svc, "request_remote_support", return_value=_session_stub()
        ) as create:
            resp = views.request_help(req)
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(create.called)

    def test_operator_accept_denies_unauthorized(self):
        req = rf.post("/x/accept/")
        req.user = _U()
        with mock.patch.object(
            views, "get_object_or_404", return_value=_session_stub()
        ), mock.patch.object(
            views, "operator_can_remote_support", return_value=False
        ):
            with self.assertRaises(PermissionDenied):
                views.operator_accept(req, session_id="sid")

    def test_operator_accept_authorized_calls_service(self):
        req = rf.post("/x/accept/")
        req.user = _U()
        with mock.patch.object(
            views, "get_object_or_404", return_value=_session_stub()
        ), mock.patch.object(
            views, "operator_can_remote_support", return_value=True
        ), mock.patch.object(
            views.svc, "accept_remote_support"
        ) as accept:
            resp = views.operator_accept(req, session_id="sid")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(accept.called)

    def test_consent_rejects_wrong_tenant(self):
        req = rf.post("/x/consent/")
        req.user = _U()
        req.school = mock.Mock(id=999)  # mismatched tenant
        with mock.patch.object(
            views, "get_object_or_404", return_value=_session_stub(school_id=1)
        ):
            with self.assertRaises(PermissionDenied):
                views.grant_consent(req, session_id="sid")

    def test_consent_allows_requester(self):
        req = rf.post("/x/consent/")
        req.user = _U()
        req.school = mock.Mock(id=1)
        with mock.patch.object(
            views, "get_object_or_404", return_value=_session_stub(school_id=1)
        ), mock.patch.object(views.svc, "record_consent") as consent:
            resp = views.grant_consent(req, session_id="sid")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(consent.called)
