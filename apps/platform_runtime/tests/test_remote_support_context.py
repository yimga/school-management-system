"""Remote Support UI — consent-banner context processor (no DB)."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.platform_runtime import context_processors as cp
from apps.platform_runtime.models_remote_support import RemoteSupportSession


class _Anon:
    is_authenticated = False


class _User:
    is_authenticated = True


def _req(user, school=None):
    r = mock.Mock()
    r.user = user
    r.school = school
    return r


class RemoteSupportContextTests(SimpleTestCase):
    def test_anonymous_returns_none(self):
        out = cp.remote_support_context(_req(_Anon()))
        self.assertIsNone(out["rmc_remote_support"])

    def test_no_school_returns_none(self):
        out = cp.remote_support_context(_req(_User(), None))
        self.assertIsNone(out["rmc_remote_support"])

    def test_accepted_pending_consent_exposes_banner(self):
        session = RemoteSupportSession(
            status=RemoteSupportSession.Status.ACCEPTED, requires_consent=True
        )
        qs = mock.Mock()
        qs.order_by.return_value.first.return_value = session
        with mock.patch.object(
            RemoteSupportSession.objects, "filter", return_value=qs
        ):
            out = cp.remote_support_context(_req(_User(), mock.Mock(pk=1)))
        banner = out["rmc_remote_support"]
        self.assertIsNotNone(banner)
        self.assertTrue(banner["needs_consent"])
        self.assertFalse(banner["is_active"])

    def test_active_session_flags_is_active(self):
        session = RemoteSupportSession(
            status=RemoteSupportSession.Status.ACTIVE, requires_consent=False
        )
        qs = mock.Mock()
        qs.order_by.return_value.first.return_value = session
        with mock.patch.object(
            RemoteSupportSession.objects, "filter", return_value=qs
        ):
            out = cp.remote_support_context(_req(_User(), mock.Mock(pk=1)))
        self.assertTrue(out["rmc_remote_support"]["is_active"])

    def test_no_open_session_returns_none(self):
        qs = mock.Mock()
        qs.order_by.return_value.first.return_value = None
        with mock.patch.object(
            RemoteSupportSession.objects, "filter", return_value=qs
        ):
            out = cp.remote_support_context(_req(_User(), mock.Mock(pk=1)))
        self.assertIsNone(out["rmc_remote_support"])
