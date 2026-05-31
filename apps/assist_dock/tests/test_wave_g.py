"""v4.00.97 Wave G — cursor co-browse + impersonation flow tests."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock import default_badges  # noqa: F401 — seed
from apps.assist_dock import default_slots  # noqa: F401 — seed
from apps.assist_dock import power_chips  # noqa: F401 — seed
from apps.assist_dock.cursors import (
    CURSOR_TTL_SECONDS,
    MAX_CURSORS_PER_PAGE,
    SELECTION_TEXT_MAX_LEN,
    CursorPing,
    _clamp_coord,
    _color_hash_for,
    _sanitize_selection,
    heartbeat as cursor_heartbeat_fn,
    list_cursors,
    reset_for_tests as reset_cursors,
)
from apps.assist_dock.impersonation import (
    GRANT_DEFAULT_TTL_SECONDS,
    GRANT_MAX_TTL_SECONDS,
    SESSION_KEY_GRANT_ID,
    SESSION_KEY_IMPERSONATOR,
    SESSION_KEY_STARTED_AT,
    clamp_ttl_seconds,
    is_super,
    session_banner_context,
)
from apps.assist_dock.middleware import (
    AssistDockImpersonationBannerMiddleware,
)
from apps.assist_dock.views_cursors import cursor_heartbeat, cursor_list


def _unwrap(func, depth=4):
    for _ in range(depth):
        inner = getattr(func, "__wrapped__", None)
        if inner is None:
            return func
        func = inner
    return func


def _super(pk=1):
    u = mock.Mock(
        spec=[
            "pk",
            "is_authenticated",
            "is_active",
            "is_superuser",
            "is_staff",
            "username",
            "primary_role",
        ]
    )
    u.pk = pk
    u.is_authenticated = True
    u.is_active = True
    u.is_superuser = True
    u.is_staff = True
    u.username = f"super{pk}"
    u.primary_role = "SUPERADMIN"
    return u


def _normal(pk=2):
    u = mock.Mock(
        spec=[
            "pk",
            "is_authenticated",
            "is_active",
            "is_superuser",
            "is_staff",
            "username",
            "primary_role",
        ]
    )
    u.pk = pk
    u.is_authenticated = True
    u.is_active = True
    u.is_superuser = False
    u.is_staff = False
    u.username = f"u{pk}"
    u.primary_role = "TEACHER"
    return u


# ---------- G1: cursor module pure-function tests ----------


class CursorSanitizationTests(SimpleTestCase):
    def test_clamp_coord_in_range(self):
        self.assertEqual(_clamp_coord(50.0), 50.0)
        self.assertEqual(_clamp_coord(0.0), 0.0)
        self.assertEqual(_clamp_coord(100.0), 100.0)

    def test_clamp_coord_clamps_low(self):
        self.assertEqual(_clamp_coord(-5.0), 0.0)

    def test_clamp_coord_clamps_high(self):
        self.assertEqual(_clamp_coord(250.0), 100.0)

    def test_clamp_coord_garbage(self):
        self.assertEqual(_clamp_coord("nope"), 0.0)
        self.assertEqual(_clamp_coord(None), 0.0)

    def test_color_hash_deterministic(self):
        self.assertEqual(_color_hash_for(7), _color_hash_for(7))
        self.assertNotEqual(_color_hash_for(7), _color_hash_for(8))

    def test_color_hash_in_range(self):
        for uid in (1, 10, 100, 99999):
            h = _color_hash_for(uid)
            self.assertTrue(0 <= h < 360)

    def test_sanitize_selection_strips_control(self):
        self.assertEqual(
            _sanitize_selection("hello\x00world\x7fend"), "helloworldend"
        )

    def test_sanitize_selection_truncates(self):
        big = "x" * (SELECTION_TEXT_MAX_LEN + 50)
        self.assertEqual(len(_sanitize_selection(big)), SELECTION_TEXT_MAX_LEN)

    def test_sanitize_selection_empty(self):
        self.assertEqual(_sanitize_selection(""), "")
        self.assertEqual(_sanitize_selection(None), "")


class CursorHeartbeatModuleTests(SimpleTestCase):
    def setUp(self):
        reset_cursors()

    def tearDown(self):
        reset_cursors()

    def test_heartbeat_records_then_lists(self):
        cursor_heartbeat_fn(user_id=10, page_path="/x/", x_pct=50, y_pct=50)
        pings = list_cursors(page_path="/x/")
        self.assertEqual(len(pings), 1)
        self.assertEqual(pings[0].user_id, 10)

    def test_heartbeat_excludes_self(self):
        cursor_heartbeat_fn(user_id=10, page_path="/x/", x_pct=10, y_pct=10)
        cursor_heartbeat_fn(user_id=11, page_path="/x/", x_pct=20, y_pct=20)
        pings = list_cursors(page_path="/x/", exclude_user_id=10)
        self.assertEqual({p.user_id for p in pings}, {11})

    def test_heartbeat_zero_user_returns_none(self):
        result = cursor_heartbeat_fn(user_id=0, page_path="/x/", x_pct=0, y_pct=0)
        self.assertIsNone(result)

    def test_heartbeat_empty_page_returns_none(self):
        result = cursor_heartbeat_fn(
            user_id=10, page_path="", x_pct=0, y_pct=0
        )
        self.assertIsNone(result)

    def test_list_cursors_caps_at_max(self):
        for uid in range(1, MAX_CURSORS_PER_PAGE + 10):
            cursor_heartbeat_fn(
                user_id=uid, page_path="/busy/", x_pct=1, y_pct=1
            )
        pings = list_cursors(page_path="/busy/", exclude_user_id=0)
        self.assertLessEqual(len(pings), MAX_CURSORS_PER_PAGE)

    def test_list_cursors_drops_stale(self):
        ping = cursor_heartbeat_fn(
            user_id=10, page_path="/x/", x_pct=1, y_pct=1
        )
        self.assertIsNotNone(ping)
        # Manually backdate the ping past TTL via reset + insert.
        from apps.assist_dock import cursors as cursors_mod

        with cursors_mod._LOCK:
            cursors_mod._BY_PAGE["/x/"][10] = CursorPing(
                user_id=10, last_seen=ping.last_seen - CURSOR_TTL_SECONDS - 10
            )
        pings = list_cursors(page_path="/x/")
        self.assertEqual(pings, [])


# ---------- G1: cursor view tests ----------


class CursorViewTests(SimpleTestCase):
    def setUp(self):
        reset_cursors()
        self.rf = RequestFactory()

    def tearDown(self):
        reset_cursors()

    def _post(self, body_dict, user=None):
        view = _unwrap(cursor_heartbeat)
        req = self.rf.post(
            "/assist-dock/cursors/heartbeat/",
            data=json.dumps(body_dict).encode("utf-8"),
            content_type="application/json",
        )
        req.user = user or _normal()
        return view(req)

    def test_bad_json_400(self):
        view = _unwrap(cursor_heartbeat)
        req = self.rf.post(
            "/assist-dock/cursors/heartbeat/",
            data=b"nope",
            content_type="application/json",
        )
        req.user = _normal()
        self.assertEqual(view(req).status_code, 400)

    def test_oversized_body_400(self):
        view = _unwrap(cursor_heartbeat)
        big_payload = "x" * 2048
        req = self.rf.post(
            "/assist-dock/cursors/heartbeat/",
            data=json.dumps({"page_path": "/x/", "selection_text": big_payload}).encode("utf-8"),
            content_type="application/json",
        )
        req.user = _normal()
        self.assertEqual(view(req).status_code, 400)

    def test_missing_page_400(self):
        self.assertEqual(self._post({"x_pct": 1, "y_pct": 1}).status_code, 400)

    def test_ok_records_ping(self):
        response = self._post(
            {"page_path": "/finance/", "x_pct": 33.3, "y_pct": 66.6}
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])

    def test_cursor_list_excludes_caller(self):
        cursor_heartbeat_fn(user_id=5, page_path="/x/", x_pct=10, y_pct=10)
        cursor_heartbeat_fn(user_id=6, page_path="/x/", x_pct=20, y_pct=20)
        view = _unwrap(cursor_list)
        req = self.rf.get("/assist-dock/cursors/list.json?page=/x/")
        req.user = _normal(pk=5)
        response = view(req)
        envelope = json.loads(response.content)
        ids = {p["user_id"] for p in envelope["cursors"]}
        self.assertEqual(ids, {6})


# ---------- G2: impersonation pure-function tests ----------


class IsSuperTests(SimpleTestCase):
    def test_anonymous_not_super(self):
        u = mock.Mock(is_authenticated=False)
        self.assertFalse(is_super(u))

    def test_none_not_super(self):
        self.assertFalse(is_super(None))

    def test_django_superuser(self):
        u = mock.Mock(spec=["is_authenticated", "is_superuser"])
        u.is_authenticated = True
        u.is_superuser = True
        self.assertTrue(is_super(u))

    def test_primary_role_superadmin(self):
        u = mock.Mock(
            spec=["is_authenticated", "is_superuser", "primary_role"]
        )
        u.is_authenticated = True
        u.is_superuser = False
        u.primary_role = "SUPERADMIN"
        self.assertTrue(is_super(u))

    def test_normal_user_not_super(self):
        u = mock.Mock(
            spec=["is_authenticated", "is_superuser", "primary_role"]
        )
        u.is_authenticated = True
        u.is_superuser = False
        u.primary_role = "TEACHER"
        self.assertFalse(is_super(u))


class ClampTTLTests(SimpleTestCase):
    def test_default_on_zero(self):
        self.assertEqual(clamp_ttl_seconds(0), GRANT_DEFAULT_TTL_SECONDS)

    def test_default_on_negative(self):
        self.assertEqual(clamp_ttl_seconds(-50), GRANT_DEFAULT_TTL_SECONDS)

    def test_default_on_garbage(self):
        self.assertEqual(clamp_ttl_seconds("nope"), GRANT_DEFAULT_TTL_SECONDS)
        self.assertEqual(clamp_ttl_seconds(None), GRANT_DEFAULT_TTL_SECONDS)

    def test_passthrough_in_range(self):
        self.assertEqual(clamp_ttl_seconds(120), 120)

    def test_clamps_to_max(self):
        self.assertEqual(
            clamp_ttl_seconds(GRANT_MAX_TTL_SECONDS * 10),
            GRANT_MAX_TTL_SECONDS,
        )


class SessionBannerContextTests(SimpleTestCase):
    def test_empty_when_no_session(self):
        req = mock.Mock(session=None)
        self.assertEqual(session_banner_context(req), {})

    def test_empty_when_no_keys(self):
        req = mock.Mock(session={})
        self.assertEqual(session_banner_context(req), {})

    def test_returns_payload_when_active(self):
        req = mock.Mock(
            session={
                SESSION_KEY_GRANT_ID: 7,
                SESSION_KEY_IMPERSONATOR: 1,
                SESSION_KEY_STARTED_AT: "2026-05-31T00:00:00",
            }
        )
        payload = session_banner_context(req)
        self.assertTrue(payload["active"])
        self.assertEqual(payload["grant_id"], 7)
        self.assertEqual(payload["impersonator_id"], 1)
        self.assertEqual(payload["started_at_iso"], "2026-05-31T00:00:00")


class ImpersonationBannerMiddlewareTests(SimpleTestCase):
    def test_sets_empty_when_no_session(self):
        captured = {}

        def downstream(request):
            captured["banner"] = getattr(request, "assist_dock_impersonation", None)
            return mock.Mock(status_code=200)

        mw = AssistDockImpersonationBannerMiddleware(downstream)
        req = mock.Mock(session=None)
        mw(req)
        self.assertEqual(captured["banner"], {})

    def test_sets_payload_when_active(self):
        captured = {}

        def downstream(request):
            captured["banner"] = getattr(request, "assist_dock_impersonation", None)
            return mock.Mock(status_code=200)

        mw = AssistDockImpersonationBannerMiddleware(downstream)
        req = mock.Mock(
            session={
                SESSION_KEY_GRANT_ID: 11,
                SESSION_KEY_IMPERSONATOR: 99,
                SESSION_KEY_STARTED_AT: "2026-05-31T00:00:00",
            }
        )
        mw(req)
        self.assertTrue(captured["banner"]["active"])
        self.assertEqual(captured["banner"]["grant_id"], 11)

    def test_never_raises(self):
        def downstream(request):
            return mock.Mock(status_code=200)

        mw = AssistDockImpersonationBannerMiddleware(downstream)
        req = mock.Mock()
        # session attribute raises on access — simulate by making get raise.
        with mock.patch(
            "apps.assist_dock.impersonation.session_banner_context",
            side_effect=RuntimeError("boom"),
        ):
            # MUST NOT raise.
            mw(req)
        self.assertEqual(req.assist_dock_impersonation, {})


# ---------- G2: request/approve/start dual-control gate (mocked DB) ----------


class RequestGrantGatingTests(SimpleTestCase):
    def test_not_super_rejected(self):
        from apps.assist_dock.impersonation import request_grant

        code, grant = request_grant(
            grantor=_normal(), target_user_id=99, reason="x"
        )
        self.assertEqual(code, "not_super")
        self.assertIsNone(grant)

    def test_self_target_rejected(self):
        from apps.assist_dock.impersonation import request_grant

        super_user = _super(pk=5)
        code, grant = request_grant(
            grantor=super_user, target_user_id=5, reason="x"
        )
        self.assertEqual(code, "self_target")
        self.assertIsNone(grant)

    def test_missing_reason_rejected(self):
        from apps.assist_dock.impersonation import request_grant

        code, grant = request_grant(
            grantor=_super(), target_user_id=2, reason="   "
        )
        self.assertEqual(code, "missing_reason")
        self.assertIsNone(grant)


class ApproveDualControlTests(SimpleTestCase):
    def test_not_super_rejected(self):
        from apps.assist_dock.impersonation import approve_grant

        code, grant = approve_grant(approver=_normal(), grant_id=1)
        self.assertEqual(code, "not_super")

    def test_lookup_failure_returns_lookup_failed(self):
        from apps.assist_dock.impersonation import approve_grant

        # No DB → ImpersonationGrant.objects.filter raises (in SimpleTestCase
        # the DB is forbidden); the broad-except clamps to lookup_failed.
        code, _ = approve_grant(approver=_super(), grant_id=999)
        self.assertIn(code, {"lookup_failed", "grant_not_found"})


class StartSessionRBACTests(SimpleTestCase):
    def test_not_super_rejected(self):
        from apps.assist_dock.impersonation import start_session_from_grant

        code, session = start_session_from_grant(
            operator=_normal(),
            grant_id=1,
            request_session={},
        )
        self.assertEqual(code, "not_super")
        self.assertIsNone(session)


class StopSessionTests(SimpleTestCase):
    def test_no_session_returns_no_session(self):
        from apps.assist_dock.impersonation import stop_session

        code, info = stop_session(operator=_super(), request_session=None)
        self.assertEqual(code, "no_session")

    def test_empty_session_returns_no_session(self):
        from apps.assist_dock.impersonation import stop_session

        code, info = stop_session(operator=_super(), request_session={})
        self.assertEqual(code, "no_session")


# ---------- G2: view layer 403 / 400 envelopes ----------


class ImpersonationViewGatingTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()

    def _post(self, view_fn, body, user):
        # Peel just the outermost (login_required) wrapper so the
        # _require_super gate is still in the stack. csrf_protect is the
        # innermost and our 403 returns BEFORE require_http_methods checks
        # the method, so the bare-method request works fine in tests.
        view = _unwrap(view_fn, depth=1)
        req = self.rf.post(
            "/x/",
            data=json.dumps(body).encode("utf-8"),
            content_type="application/json",
        )
        req.user = user
        # Mark CSRF-checked so csrf_protect inside the stack doesn't reject.
        req._dont_enforce_csrf_checks = True
        return view(req)

    def test_request_view_normal_user_403(self):
        from apps.assist_dock.views_impersonation import impersonation_request

        response = self._post(
            impersonation_request,
            {"target_user_id": 2, "reason": "audit"},
            _normal(),
        )
        self.assertEqual(response.status_code, 403)

    def test_approve_view_normal_user_403(self):
        from apps.assist_dock.views_impersonation import impersonation_approve

        response = self._post(
            impersonation_approve, {"grant_id": 1}, _normal()
        )
        self.assertEqual(response.status_code, 403)

    def test_start_view_normal_user_403(self):
        from apps.assist_dock.views_impersonation import impersonation_start

        response = self._post(impersonation_start, {"grant_id": 1}, _normal())
        self.assertEqual(response.status_code, 403)

    def test_revoke_view_normal_user_403(self):
        from apps.assist_dock.views_impersonation import impersonation_revoke

        response = self._post(impersonation_revoke, {"grant_id": 1}, _normal())
        self.assertEqual(response.status_code, 403)

    def test_stop_view_works_for_non_super(self):
        """Stop is auth-only (any user can end impersonation in their own session)."""
        from apps.assist_dock.views_impersonation import impersonation_stop

        response = self._post(impersonation_stop, {}, _normal())
        # No session → 400 with error=no_session (NOT 403).
        self.assertEqual(response.status_code, 400)
        envelope = json.loads(response.content)
        self.assertEqual(envelope["error"], "no_session")
