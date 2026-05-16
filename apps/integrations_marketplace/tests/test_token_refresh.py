"""Tests for `apps.integrations_marketplace.token_refresh` (v2.79).

Covers the pure-Python pieces (`_is_due`, the HTTP/JSON envelope helpers) as
SimpleTestCase + targeted unittest.mock patches; covers `refresh_single`'s
state-machine transitions against an in-memory fake row object so we don't
require a live DB (the test runner has historically struggled to spin up the
sqlite test DB on Windows when prior crashed runs leave a lock file).
"""

from __future__ import annotations

import time
from unittest import mock

from django.test import SimpleTestCase

from apps.integrations_marketplace import token_refresh
from apps.integrations_marketplace.token_refresh import (
    DEFAULT_LIFETIME_SECONDS,
    NO_EXPIRY_RECORDED_MAX_AGE,
    REFRESH_WINDOW_SECONDS,
    _is_due,
    refresh_single,
)


class _FakeRow:
    """Minimal duck-typed stand-in for a ServiceIntegration row."""

    def __init__(self, *, pk=1, slug="zoom", config=None, is_active=True):
        self.pk = pk
        self.connector_slug = slug
        self.config = dict(config or {})
        self.is_active = is_active
        self.saved_with_fields: list[list[str]] = []

    def save(self, update_fields=None):
        self.saved_with_fields.append(list(update_fields or []))


class IsDueTests(SimpleTestCase):
    def test_returns_false_when_config_missing_refresh_token(self):
        self.assertFalse(_is_due({}))
        self.assertFalse(_is_due({"access_token": "a"}))

    def test_returns_false_for_non_dict_config(self):
        self.assertFalse(_is_due(None))  # type: ignore[arg-type]
        self.assertFalse(_is_due("not a dict"))  # type: ignore[arg-type]

    def test_returns_true_when_expires_at_inside_window(self):
        now = 1_000_000.0
        cfg = {"refresh_token": "r", "expires_at": now + REFRESH_WINDOW_SECONDS - 1}
        self.assertTrue(_is_due(cfg, now=now))

    def test_returns_false_when_expires_at_outside_window(self):
        now = 1_000_000.0
        cfg = {"refresh_token": "r", "expires_at": now + REFRESH_WINDOW_SECONDS + 60}
        self.assertFalse(_is_due(cfg, now=now))

    def test_fallback_path_uses_issued_at_when_no_expires_at(self):
        now = 1_000_000.0
        # issued_at is older than fallback max age — should be due.
        cfg = {"refresh_token": "r", "issued_at": now - NO_EXPIRY_RECORDED_MAX_AGE - 1}
        self.assertTrue(_is_due(cfg, now=now))
        # issued_at is recent — should NOT be due.
        cfg["issued_at"] = now - 60
        self.assertFalse(_is_due(cfg, now=now))

    def test_fallback_path_handles_garbage_issued_at(self):
        cfg = {"refresh_token": "r", "issued_at": "not-a-number"}
        # Treated as 0 → forces due.
        self.assertTrue(_is_due(cfg, now=time.time()))


class RefreshSingleStateMachineTests(SimpleTestCase):
    def setUp(self):
        # Plant a valid client credential pair so the credential-skip branch
        # doesn't short-circuit the path under test.
        self._cred_patch = mock.patch.object(
            token_refresh,
            "resolve_oauth_client_credentials",
            return_value=("cid", "csecret"),
        )
        self._cred_patch.start()

    def tearDown(self):
        self._cred_patch.stop()

    def _row(self, **kwargs):
        cfg = {"refresh_token": "rtok", "access_token": "old"}
        cfg.update(kwargs.pop("config", {}))
        return _FakeRow(config=cfg, **kwargs)

    def test_skips_when_slug_is_unknown(self):
        row = _FakeRow(slug="not-a-real-connector", config={"refresh_token": "r"})
        with mock.patch.object(token_refresh, "get_connector", return_value=None):
            result = refresh_single(row)
        self.assertEqual(result["status"], "skipped_non_oauth")
        self.assertEqual(row.saved_with_fields, [])

    def test_skips_when_no_refresh_token(self):
        row = _FakeRow(config={})
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2, token_url="x")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn):
            result = refresh_single(row)
        self.assertEqual(result["status"], "skipped_no_refresh_token")
        self.assertEqual(row.saved_with_fields, [])

    def test_skips_when_platform_credentials_missing(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2, token_url="x")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "resolve_oauth_client_credentials",
                               return_value=("", "")):
            result = refresh_single(row)
        self.assertEqual(result["status"], "skipped_missing_platform_credentials")
        self.assertEqual(row.saved_with_fields, [])

    def test_transport_error_stamps_last_refresh_error_and_keeps_row_active(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(0, {})):
            result = refresh_single(row)
        self.assertEqual(result["status"], "transport_error")
        self.assertEqual(row.config["last_refresh_error"], "transport_error")
        self.assertTrue(row.is_active)  # Transport hiccup must NOT deactivate.

    def test_invalid_grant_deactivates_row_and_stamps_disconnect_reason(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(400, {"error": "invalid_grant"})):
            result = refresh_single(row)
        self.assertEqual(result["status"], "deactivated_invalid_grant")
        self.assertFalse(row.is_active)
        self.assertEqual(row.config["disconnect_reason"], "invalid_grant")
        self.assertEqual(row.config["last_refresh_error"], "invalid_grant")

    def test_generic_4xx_marks_failure_but_keeps_active(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(429, {"error": "rate_limited"})):
            result = refresh_single(row)
        self.assertEqual(result["status"], "refresh_failed")
        self.assertEqual(result["http_status"], 429)
        self.assertTrue(row.is_active)

    def test_success_updates_access_token_and_clears_error_fields(self):
        row = self._row(config={"last_refresh_error": "previous_error",
                                "disconnect_reason": "previous_invalid"})
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(200, {
                                   "access_token": "new-bearer",
                                   "expires_in": 3600,
                               })):
            result = refresh_single(row)
        self.assertEqual(result["status"], "refreshed")
        self.assertEqual(row.config["access_token"], "new-bearer")
        self.assertNotIn("last_refresh_error", row.config)
        self.assertNotIn("disconnect_reason", row.config)
        self.assertTrue(row.is_active)
        self.assertIn("expires_at", row.config)
        self.assertIn("issued_at", row.config)

    def test_rotated_refresh_token_is_persisted(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(200, {
                                   "access_token": "new",
                                   "refresh_token": "rotated",
                                   "expires_in": 1800,
                               })):
            refresh_single(row)
        self.assertEqual(row.config["refresh_token"], "rotated")

    def test_missing_access_token_in_200_response_marks_failure(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(200, {"expires_in": 3600})):
            result = refresh_single(row)
        self.assertEqual(result["status"], "refresh_failed_no_token")
        self.assertEqual(row.config["last_refresh_error"], "no_access_token_in_response")

    def test_garbage_expires_in_falls_back_to_default_lifetime(self):
        row = self._row()
        fake_conn = mock.Mock(auth_kind=token_refresh.AUTH_KIND_OAUTH2,
                              token_url="https://example/token")
        before = time.time()
        with mock.patch.object(token_refresh, "get_connector", return_value=fake_conn), \
             mock.patch.object(token_refresh, "_post_token_refresh",
                               return_value=(200, {
                                   "access_token": "x",
                                   "expires_in": "not-an-int",
                               })):
            refresh_single(row)
        self.assertGreaterEqual(
            row.config["expires_at"], before + DEFAULT_LIFETIME_SECONDS - 5
        )


class CeleryTaskExportTests(SimpleTestCase):
    def test_celery_task_is_registered_with_expected_name(self):
        # When celery is importable, the decorator should produce a task with
        # the documented name; when not, it should be exported as None and
        # the underlying function remains usable.
        task = token_refresh.refresh_due_oauth_tokens_task
        if task is None:
            # Celery not installed in this env — confirm bare function still works.
            self.assertTrue(callable(token_refresh.refresh_due_oauth_tokens))
            return
        self.assertEqual(getattr(task, "name", None),
                         "integrations_marketplace.refresh_due_oauth_tokens")
