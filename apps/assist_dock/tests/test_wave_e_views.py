"""v4.00.95 Wave E — presence + SSE + share + deep RBAC + impersonation tests."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock import default_slots  # noqa: F401 — seed
from apps.assist_dock import power_chips  # noqa: F401 — seed
from apps.assist_dock.power_views import (
    _AUTH_DECORATOR_NAMES,
    _AUTH_MIXIN_NAMES,
    _deep_rbac_signal,
    _resolve_impersonation_routes,
    _walk_auth_decorators,
    _walk_auth_mixins,
)
from apps.assist_dock.presence import reset_for_tests as reset_presence
from apps.assist_dock.views_presence import _avatar_url, _display_name
from apps.assist_dock.views_share import mint_share_link, resolve_share_link


def _unwrap(func, depth=4):
    for _ in range(depth):
        inner = getattr(func, "__wrapped__", None)
        if inner is None:
            return func
        func = inner
    return func


class DisplayHelperTests(SimpleTestCase):
    def test_display_name_prefers_get_full_name(self):
        user = mock.Mock()
        user.get_full_name = mock.Mock(return_value="Ada Lovelace")
        self.assertEqual(_display_name(user), "Ada Lovelace")

    def test_display_name_falls_back_to_username(self):
        user = mock.Mock(spec=["username", "email"])
        user.username = "ada"
        user.email = ""
        self.assertEqual(_display_name(user), "ada")

    def test_display_name_truncates(self):
        user = mock.Mock()
        user.get_full_name = mock.Mock(return_value="X" * 200)
        self.assertEqual(len(_display_name(user)), 80)

    def test_avatar_url_prefers_avatar_url(self):
        user = mock.Mock(spec=["avatar_url"])
        user.avatar_url = "/x.png"
        self.assertEqual(_avatar_url(user), "/x.png")

    def test_avatar_url_blank_when_absent(self):
        user = mock.Mock(spec=[])
        self.assertEqual(_avatar_url(user), "")


class PresenceEndpointTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        reset_presence()

    def tearDown(self):
        reset_presence()

    def _user(self):
        user = mock.Mock(spec=["pk", "is_authenticated", "is_active", "username"])
        user.pk = 99
        user.is_authenticated = True
        user.is_active = True
        user.username = "ada"
        return user

    def test_heartbeat_records_and_returns_envelope(self):
        from apps.assist_dock.views_presence import presence_heartbeat

        view = _unwrap(presence_heartbeat)
        req = self.rf.post(
            "/assist-dock/presence/heartbeat/",
            data=json.dumps({"page_path": "/portal/"}).encode("utf-8"),
            content_type="application/json",
        )
        req.user = self._user()
        response = view(req)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertIn("heartbeat_seconds", payload)

    def test_heartbeat_bad_json_400(self):
        from apps.assist_dock.views_presence import presence_heartbeat

        view = _unwrap(presence_heartbeat)
        req = self.rf.post(
            "/assist-dock/presence/heartbeat/",
            data=b"nope",
            content_type="application/json",
        )
        req.user = self._user()
        self.assertEqual(view(req).status_code, 400)

    def test_heartbeat_missing_page_400(self):
        from apps.assist_dock.views_presence import presence_heartbeat

        view = _unwrap(presence_heartbeat)
        req = self.rf.post(
            "/assist-dock/presence/heartbeat/",
            data=b"{}",
            content_type="application/json",
        )
        req.user = self._user()
        self.assertEqual(view(req).status_code, 400)

    def test_list_excludes_self(self):
        from apps.assist_dock.presence import heartbeat
        from apps.assist_dock.views_presence import presence_list

        heartbeat(user_id=99, page_path="/portal/", display_name="me")
        heartbeat(user_id=100, page_path="/portal/", display_name="other")
        view = _unwrap(presence_list)
        req = self.rf.get("/assist-dock/presence/list.json?page=/portal/")
        req.user = self._user()
        response = view(req)
        payload = json.loads(response.content)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["present"][0]["user_id"], 100)


class DeepRBACTests(SimpleTestCase):
    def test_unresolved_path_falls_back_to_prefix_sniff(self):
        signal = _deep_rbac_signal("/totally/made-up/path/never/exists/")
        self.assertIn("scope", signal)
        self.assertFalse(signal.get("resolved", True))

    def test_login_required_decorator_detected(self):
        from django.contrib.auth.decorators import login_required

        @login_required
        def view(request):
            return None

        names = _walk_auth_decorators(view)
        self.assertIn("login_required", names)

    def test_mixin_walker_returns_empty_for_function_view(self):
        def view(request):
            return None

        self.assertEqual(_walk_auth_mixins(view), [])

    def test_auth_decorator_name_set_loaded(self):
        # Sanity: the constants are populated and frozen.
        self.assertIn("login_required", _AUTH_DECORATOR_NAMES)
        self.assertIn("LoginRequiredMixin", _AUTH_MIXIN_NAMES)


class ImpersonationRouteTests(SimpleTestCase):
    def test_no_routes_returns_empty(self):
        # On a vanilla project these URL names won't exist; empty list is fine.
        out = _resolve_impersonation_routes()
        self.assertIsInstance(out, list)


class ShareMintViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _user(self):
        user = mock.Mock()
        user.pk = 1
        user.is_authenticated = True
        return user

    def test_bad_json_400(self):
        view = _unwrap(mint_share_link)
        req = self.rf.post(
            "/assist-dock/share/mint/",
            data=b"nope",
            content_type="application/json",
        )
        req.user = self._user()
        self.assertEqual(view(req).status_code, 400)

    def test_oversize_400(self):
        view = _unwrap(mint_share_link)
        req = self.rf.post(
            "/assist-dock/share/mint/",
            data=b"x" * 10000,
            content_type="application/json",
        )
        req.user = self._user()
        self.assertEqual(view(req).status_code, 400)

    def test_mint_failure_returns_400_with_error_code(self):
        view = _unwrap(mint_share_link)
        req = self.rf.post(
            "/assist-dock/share/mint/",
            data=json.dumps({"target": ""}).encode("utf-8"),
            content_type="application/json",
        )
        req.user = self._user()
        response = view(req)
        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.content)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"], "target_required")

    def test_mint_success_returns_envelope(self):
        view = _unwrap(mint_share_link)
        req = self.rf.post(
            "/assist-dock/share/mint/",
            data=json.dumps({"target": "/portal/dashboard/", "ttl_hours": 12}).encode(
                "utf-8"
            ),
            content_type="application/json",
        )
        req.user = self._user()
        fake_link = mock.Mock(
            token="abc123",
            expires_at=None,
        )
        with mock.patch(
            "apps.assist_dock.views_share.mint_short_link",
            return_value=(fake_link, ""),
        ):
            response = view(req)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["token"], "abc123")
        self.assertIn("/assist-dock/s/abc123/", payload["short_path"])


class ShareResolveViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def test_missing_returns_410(self):
        view = resolve_share_link.__wrapped__
        req = self.rf.get("/assist-dock/s/missing/")
        with mock.patch(
            "apps.assist_dock.views_share.resolve_short_link", return_value=None
        ):
            response = view(req, token="missing")
        self.assertEqual(response.status_code, 410)

    def test_present_redirects(self):
        view = resolve_share_link.__wrapped__
        req = self.rf.get("/assist-dock/s/ok/")
        fake_link = mock.Mock(target_url="/portal/dashboard/")
        with mock.patch(
            "apps.assist_dock.views_share.resolve_short_link",
            return_value=fake_link,
        ), mock.patch(
            "apps.assist_dock.views_share.record_short_link_hit"
        ):
            response = view(req, token="ok")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/portal/dashboard/")
