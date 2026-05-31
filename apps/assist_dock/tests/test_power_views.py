"""v4.00.93 Wave C — power chip landing view tests."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock.power_views import (
    _sanitize_next_url,
    _try_rbac_signal,
    _try_site_settings_keys,
    prefs_view,
)


class SanitizeNextUrlTests(SimpleTestCase):
    def test_empty_returns_root(self):
        self.assertEqual(_sanitize_next_url(""), "/")

    def test_absolute_url_rejected(self):
        self.assertEqual(_sanitize_next_url("https://evil/"), "/")

    def test_protocol_relative_rejected(self):
        self.assertEqual(_sanitize_next_url("//evil/foo"), "/")

    def test_relative_allowed(self):
        self.assertEqual(_sanitize_next_url("/portal/dashboard/"), "/portal/dashboard/")

    def test_truncated_to_512(self):
        long = "/" + "x" * 1000
        self.assertEqual(len(_sanitize_next_url(long)), 512)


class RbacSignalTests(SimpleTestCase):
    def test_super_path_scope(self):
        self.assertIn("super-staff", _try_rbac_signal("/super/migration/")["scope"])

    def test_admin_path_scope(self):
        self.assertIn("django-admin", _try_rbac_signal("/admin/auth/user/")["scope"])

    def test_portal_path_scope(self):
        self.assertIn("tenant-portal", _try_rbac_signal("/portal/dashboard/")["scope"])

    def test_other_path_scope(self):
        self.assertEqual(_try_rbac_signal("/other/")["scope"], "public")


class SiteSettingsKeysHelperTests(SimpleTestCase):
    def test_no_school_returns_empty(self):
        request = mock.Mock(spec=["school"])
        request.school = None
        self.assertEqual(_try_site_settings_keys(request), [])

    def test_import_error_returns_empty(self):
        request = mock.Mock()
        request.school = mock.Mock()
        with mock.patch.dict("sys.modules", {"apps.siteconfig.models": None}):
            with mock.patch(
                "builtins.__import__", side_effect=ImportError("no module")
            ):
                self.assertEqual(_try_site_settings_keys(request), [])


class PrefsViewLogicTests(SimpleTestCase):
    """Test the view's inner logic by calling the undecorated function.

    The decorator stack (@login_required + @require_http_methods +
    @csrf_protect) is verified separately by the URL gate; here we focus
    on payload parsing + sanitization + save dispatch.
    """

    def setUp(self):
        self.rf = RequestFactory()

    def _build_user(self):
        return mock.Mock(is_authenticated=True, is_active=True, pk=42)

    def _call_inner(self, request):
        """Reach past the three decorator wrappers to the raw function."""
        # csrf_protect uses csrf_view_decorator which sets __wrapped__;
        # require_http_methods also sets __wrapped__; login_required wraps
        # with functools.wraps, also __wrapped__. So three unwraps land on
        # the bare prefs_view function.
        func = prefs_view
        for _ in range(4):
            inner = getattr(func, "__wrapped__", None)
            if inner is None:
                break
            func = inner
        return func(request)

    def test_get_returns_payload(self):
        req = self.rf.get("/assist-dock/prefs.json")
        req.user = self._build_user()
        with mock.patch(
            "apps.assist_dock.models.get_or_default_prefs",
            return_value={"density": "cozy", "side": "right"},
        ):
            response = self._call_inner(req)
        payload = json.loads(response.content)
        self.assertIn("payload", payload)
        self.assertEqual(payload["payload"]["density"], "cozy")

    def test_post_bad_json_returns_400(self):
        req = self.rf.post(
            "/assist-dock/prefs.json",
            data=b"not-json",
            content_type="application/json",
        )
        req.user = self._build_user()
        response = self._call_inner(req)
        self.assertEqual(response.status_code, 400)

    def test_post_non_object_returns_400(self):
        req = self.rf.post(
            "/assist-dock/prefs.json",
            data=b'["a","b"]',
            content_type="application/json",
        )
        req.user = self._build_user()
        response = self._call_inner(req)
        self.assertEqual(response.status_code, 400)

    def test_post_valid_payload_saves(self):
        body = json.dumps(
            {"density": "compact", "side": "left", "halo_enabled": False}
        ).encode("utf-8")
        req = self.rf.post(
            "/assist-dock/prefs.json",
            data=body,
            content_type="application/json",
        )
        req.user = self._build_user()
        with mock.patch(
            "apps.assist_dock.models.UserAssistDockPrefs.objects.update_or_create",
            return_value=(mock.Mock(), True),
        ):
            response = self._call_inner(req)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["saved"])
        self.assertEqual(payload["payload"]["density"], "compact")
        self.assertEqual(payload["payload"]["side"], "left")
        self.assertFalse(payload["payload"]["halo_enabled"])
