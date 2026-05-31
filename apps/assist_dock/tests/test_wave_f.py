"""v4.00.96 Wave F — locale middleware + wave handler + recipient picker tests."""

from __future__ import annotations

import json
from unittest import mock

from django.test import RequestFactory, SimpleTestCase

from apps.assist_dock import default_slots  # noqa: F401 — seed
from apps.assist_dock import power_chips  # noqa: F401 — seed
from apps.assist_dock.middleware import AssistDockLocaleMiddleware
from apps.assist_dock.models import (
    _validate_locale_preference,
    coerce_payload,
    default_prefs_payload,
)
from apps.assist_dock.presence import heartbeat, reset_for_tests as reset_presence
from apps.assist_dock.views_share import _build_email_body, _sanitize_recipients
from apps.assist_dock.views_wave import (
    reset_rate_limiter_for_tests,
    wave_at_view,
)


def _unwrap(func, depth=4):
    for _ in range(depth):
        inner = getattr(func, "__wrapped__", None)
        if inner is None:
            return func
        func = inner
    return func


# ---------- F3: locale preference validation + middleware ----------


class LocalePreferenceValidationTests(SimpleTestCase):
    def test_empty_returns_empty(self):
        self.assertEqual(_validate_locale_preference(""), "")

    def test_short_code_accepted(self):
        self.assertEqual(_validate_locale_preference("en"), "en")
        self.assertEqual(_validate_locale_preference("fr"), "fr")

    def test_region_variant_accepted(self):
        self.assertEqual(_validate_locale_preference("en-US"), "en-us")
        self.assertEqual(_validate_locale_preference("zh_Hans"), "zh_hans")

    def test_garbage_rejected(self):
        for bad in ("???", "x", "way-too-long-locale-code-12345", "<script>"):
            self.assertEqual(_validate_locale_preference(bad), "")

    def test_coerce_payload_persists_locale(self):
        out = coerce_payload({"locale_preference": "en-US"})
        self.assertEqual(out["locale_preference"], "en-us")

    def test_coerce_payload_drops_invalid(self):
        out = coerce_payload({"locale_preference": "javascript:alert(1)"})
        self.assertEqual(out["locale_preference"], "")

    def test_default_payload_carries_blank_locale(self):
        self.assertEqual(default_prefs_payload()["locale_preference"], "")


class LocaleMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.called_with = []
        self.middleware = AssistDockLocaleMiddleware(self._capture_response)

    def _capture_response(self, request):
        self.called_with.append(getattr(request, "LANGUAGE_CODE", ""))
        return mock.Mock(status_code=200)

    def test_anonymous_user_no_override(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=False)
        req.LANGUAGE_CODE = "en"
        self.middleware(req)
        self.assertEqual(self.called_with[-1], "en")

    def test_authed_user_no_preference_no_override(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=True, pk=1)
        req.LANGUAGE_CODE = "en"
        with mock.patch(
            "apps.assist_dock.models.get_or_default_prefs",
            return_value=default_prefs_payload(),
        ):
            self.middleware(req)
        self.assertEqual(self.called_with[-1], "en")

    def test_authed_user_preference_overrides(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=True, pk=1)
        req.LANGUAGE_CODE = "en"
        payload = default_prefs_payload()
        payload["locale_preference"] = "fr"
        with mock.patch(
            "apps.assist_dock.models.get_or_default_prefs",
            return_value=payload,
        ), self.settings(LANGUAGES=[("en", "English"), ("fr", "French")]):
            self.middleware(req)
        self.assertEqual(self.called_with[-1], "fr")

    def test_unknown_locale_silently_ignored(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=True, pk=1)
        req.LANGUAGE_CODE = "en"
        payload = default_prefs_payload()
        payload["locale_preference"] = "qq"
        with mock.patch(
            "apps.assist_dock.models.get_or_default_prefs",
            return_value=payload,
        ), self.settings(LANGUAGES=[("en", "English")]):
            self.middleware(req)
        self.assertEqual(self.called_with[-1], "en")

    def test_middleware_never_raises(self):
        req = self.rf.get("/")
        req.user = mock.Mock(is_authenticated=True, pk=1)
        with mock.patch(
            "apps.assist_dock.models.get_or_default_prefs",
            side_effect=RuntimeError("boom"),
        ):
            # Should not raise — request flows through.
            self.middleware(req)
        self.assertTrue(self.called_with)


# ---------- F2: wave handler ----------


class WaveAtViewTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        reset_presence()
        reset_rate_limiter_for_tests()

    def tearDown(self):
        reset_presence()
        reset_rate_limiter_for_tests()

    def _user(self, pk=1):
        u = mock.Mock(spec=["pk", "is_authenticated", "is_active", "username"])
        u.pk = pk
        u.is_authenticated = True
        u.is_active = True
        u.username = f"u{pk}"
        return u

    def _post(self, body_dict, user_pk=1):
        view = _unwrap(wave_at_view)
        req = self.rf.post(
            "/assist-dock/wave/",
            data=json.dumps(body_dict).encode("utf-8"),
            content_type="application/json",
        )
        req.user = self._user(pk=user_pk)
        return view(req)

    def test_bad_json_400(self):
        view = _unwrap(wave_at_view)
        req = self.rf.post("/assist-dock/wave/", data=b"nope", content_type="application/json")
        req.user = self._user()
        self.assertEqual(view(req).status_code, 400)

    def test_missing_target_400(self):
        self.assertEqual(self._post({"page_path": "/x/"}).status_code, 400)

    def test_missing_page_400(self):
        self.assertEqual(self._post({"target_user_id": 2}).status_code, 400)

    def test_self_target_400(self):
        self.assertEqual(
            self._post({"target_user_id": 1, "page_path": "/x/"}, user_pk=1).status_code,
            400,
        )

    def test_target_not_present_403(self):
        # Target user not in presence list → forbidden.
        self.assertEqual(
            self._post({"target_user_id": 99, "page_path": "/finance/"}).status_code,
            403,
        )

    def test_present_target_succeeds(self):
        heartbeat(user_id=2, page_path="/finance/", display_name="Bob")
        response = self._post({"target_user_id": 2, "page_path": "/finance/"})
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["insight_id"].startswith("wave-"))

    def test_rate_limit_blocks_second_in_window(self):
        heartbeat(user_id=2, page_path="/finance/", display_name="Bob")
        first = self._post({"target_user_id": 2, "page_path": "/finance/"})
        self.assertEqual(first.status_code, 200)
        second = self._post({"target_user_id": 2, "page_path": "/finance/"})
        self.assertEqual(second.status_code, 429)
        envelope = json.loads(second.content)
        self.assertEqual(envelope["error"], "rate_limited")


# ---------- F4: recipient sanitization + email body ----------


class RecipientSanitizationTests(SimpleTestCase):
    def test_blank_rejected(self):
        self.assertEqual(_sanitize_recipients(["", "  ", None]), [])

    def test_lowercased_and_deduped(self):
        out = _sanitize_recipients(["Alice@Example.org", "alice@example.org", "bob@example.org"])
        self.assertEqual(out, ["alice@example.org", "bob@example.org"])

    def test_invalid_shapes_rejected(self):
        out = _sanitize_recipients(["nope", "no spaces@x.org", "x@nodot", "@no.local"])
        self.assertEqual(out, [])

    def test_capped_at_12(self):
        big = [f"u{i}@example.org" for i in range(25)]
        out = _sanitize_recipients(big)
        self.assertEqual(len(out), 12)


class EmailBodyTests(SimpleTestCase):
    def test_includes_url_and_ttl(self):
        body = _build_email_body(
            sender_label="Ada",
            absolute_url="https://app/portal/x/",
            note="",
            ttl_hours=24,
        )
        self.assertIn("https://app/portal/x/", body)
        self.assertIn("24 hour", body)
        self.assertIn("Ada", body)

    def test_optional_note_included(self):
        body = _build_email_body(
            sender_label="Ada", absolute_url="https://app/x/", note="Hi!", ttl_hours=12
        )
        self.assertIn("Hi!", body)


# ---------- F1: presence DB mirror ----------


class PresenceDBMirrorTests(SimpleTestCase):
    def setUp(self):
        reset_presence()

    def tearDown(self):
        reset_presence()

    def test_memory_path_returns_entries(self):
        from apps.assist_dock.presence import list_present

        heartbeat(user_id=10, page_path="/x/", display_name="A")
        heartbeat(user_id=11, page_path="/x/", display_name="B")
        out = list_present(page_path="/x/")
        self.assertEqual({e.user_id for e in out}, {10, 11})

    def test_db_fallback_merged_when_memory_empty(self):
        from apps.assist_dock.presence import list_present

        fake_row = mock.Mock(
            user_id=42,
            display_name="Cross-worker user",
            avatar_url="",
            first_seen=mock.Mock(timestamp=mock.Mock(return_value=100.0)),
            last_seen=mock.Mock(timestamp=mock.Mock(return_value=101.0)),
        )
        fake_qs = mock.MagicMock()
        fake_qs.__iter__ = lambda self: iter([fake_row])
        fake_objects = mock.Mock()
        fake_objects.filter.return_value.exclude.return_value.order_by.return_value.__getitem__ = lambda self, k: [fake_row]
        fake_model = mock.Mock(objects=fake_objects)
        with mock.patch.dict("sys.modules", {"apps.assist_dock.models": mock.Mock(PresencePing=fake_model)}):
            out = list_present(page_path="/finance/")
        # Memory was empty + DB returned one row → merged in.
        self.assertEqual({e.user_id for e in out}, {42})

    def test_sweep_db_presence_returns_int_on_failure(self):
        from apps.assist_dock.presence import sweep_db_presence

        with mock.patch.dict("sys.modules", {"apps.assist_dock.models": None}):
            with mock.patch("builtins.__import__", side_effect=ImportError("no mod")):
                self.assertEqual(sweep_db_presence(), 0)
