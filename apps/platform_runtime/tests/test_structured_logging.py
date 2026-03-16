"""
Tests for platform_runtime.structured_logging (§2.4 exception discipline).

Verifies log_exception_with_context, request_context_for_log, and log_view_exception
attach tenant/actor/route context correctly for audit. No DB required.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.platform_runtime.structured_logging import (
    log_exception_with_context,
    log_view_exception,
    request_context_for_log,
)


class RequestContextForLogTests(SimpleTestCase):
    """request_context_for_log extracts tenant/actor/route from request."""

    def test_extracts_school_tenant_actor_route(self) -> None:
        request = MagicMock()
        request.school = MagicMock(id=100)
        request.user = MagicMock(id=200)
        request.path = "/portal/dashboard/"
        out = request_context_for_log(request)
        self.assertEqual(out["school_id"], "100")
        self.assertEqual(out["tenant_id"], "100")
        self.assertEqual(out["actor_id"], "200")
        self.assertEqual(out["route"], "/portal/dashboard/")

    def test_empty_when_no_school_or_user(self) -> None:
        request = MagicMock(spec=["path"])
        request.path = "/login/"
        del request.school
        del request.user
        out = request_context_for_log(request)
        self.assertEqual(out, {"route": "/login/"})

    def test_handles_missing_attributes(self) -> None:
        request = MagicMock()
        request.school = None
        request.user = None
        request.path = None
        out = request_context_for_log(request)
        self.assertEqual(out, {})

    def test_includes_tenant_id_when_school_present(self) -> None:
        request = MagicMock()
        request.school = MagicMock(id=1)
        request.user = MagicMock(id=2)
        request.path = "/x/"
        out = request_context_for_log(request)
        self.assertIn("tenant_id", out)


class LogExceptionWithContextTests(SimpleTestCase):
    """log_exception_with_context merges context into extra and calls logger.warning."""

    @patch("apps.platform_runtime.structured_logging.logger")
    def test_adds_context_to_extra(self, mock_logger: MagicMock) -> None:
        log_exception_with_context(
            "test failure",
            school_id=42,
            tenant_id="42",
            actor_id=99,
            route="/api/foo",
            exc_info=False,
            extra={"custom": "value"},
        )
        mock_logger.warning.assert_called_once()
        args, kwargs = mock_logger.warning.call_args
        self.assertEqual(args[0], "test failure")
        self.assertFalse(kwargs["exc_info"])
        extra = kwargs["extra"]
        self.assertEqual(extra["school_id"], "42")
        self.assertEqual(extra["tenant_id"], "42")
        self.assertEqual(extra["actor_id"], "99")
        self.assertEqual(extra["route"], "/api/foo")
        self.assertEqual(extra["custom"], "value")

    @patch("apps.platform_runtime.structured_logging.logger")
    def test_omits_none_context_fields(self, mock_logger: MagicMock) -> None:
        log_exception_with_context("msg", exc_info=False)
        _, kwargs = mock_logger.warning.call_args
        self.assertNotIn("tenant_id", kwargs["extra"])
        self.assertNotIn("school_id", kwargs["extra"])

    @patch("apps.platform_runtime.structured_logging.logger")
    def test_exc_info_default_true(self, mock_logger: MagicMock) -> None:
        log_exception_with_context("msg", school_id=1)
        _, kwargs = mock_logger.warning.call_args
        self.assertTrue(kwargs["exc_info"])


class LogViewExceptionTests(SimpleTestCase):
    """log_view_exception builds context from request and calls log_exception_with_context."""

    @patch("apps.platform_runtime.structured_logging.log_exception_with_context")
    def test_passes_request_context_through(self, mock_log: MagicMock) -> None:
        request = MagicMock()
        request.school = MagicMock(id=10)
        request.user = MagicMock(id=20)
        request.path = "/siteconfig/theme/"
        log_view_exception(request, "theme save failed", extra={"step": "redirect"})
        mock_log.assert_called_once()
        call_kw = mock_log.call_args[1]
        self.assertEqual(call_kw["school_id"], "10")
        self.assertEqual(call_kw["tenant_id"], "10")
        self.assertEqual(call_kw["actor_id"], "20")
        self.assertEqual(call_kw["route"], "/siteconfig/theme/")
        self.assertEqual(call_kw["extra"], {"step": "redirect"})

    @patch("apps.platform_runtime.structured_logging.log_exception_with_context")
    def test_handles_none_request(self, mock_log: MagicMock) -> None:
        log_view_exception(None, "no request")
        mock_log.assert_called_once()
        call_kw = mock_log.call_args[1]
        self.assertIsNone(call_kw.get("school_id"))
        self.assertIsNone(call_kw.get("tenant_id"))
