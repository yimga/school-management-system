"""HealthAwareTenantMainMiddleware — Render /health/ must not 500 on Postgres blips."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.db.utils import OperationalError
from django.http import JsonResponse
from django.test import RequestFactory, SimpleTestCase

from django_tenants.middleware.main import TenantMainMiddleware

from apps.schools.middleware_tenant_main import (
    HealthAwareTenantMainMiddleware,
    health_probe_degraded_response,
    is_health_probe_path,
)


class HealthProbePathTests(SimpleTestCase):
    def test_recognizes_health_paths(self):
        self.assertTrue(is_health_probe_path("/health/"))
        self.assertTrue(is_health_probe_path("/api/health/"))
        self.assertFalse(is_health_probe_path("/super/"))


class HealthAwareTenantMainMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.middleware = HealthAwareTenantMainMiddleware(lambda request: JsonResponse({}))

    def test_health_path_routes_to_health_probe_handler(self):
        request = self.rf.get("/health/")
        with patch.object(
            HealthAwareTenantMainMiddleware,
            "_process_health_probe",
            return_value=None,
        ) as mock_probe:
            result = self.middleware.process_request(request)
        self.assertIsNone(result)
        mock_probe.assert_called_once_with(request)

    def test_health_probe_uses_public_urlconf_without_db(self):
        request = self.rf.get("/health/")
        mock_conn = MagicMock()
        with patch("apps.schools.middleware_tenant_main.connection", mock_conn):
            with patch("django.conf.settings.PUBLIC_SCHEMA_URLCONF", "config.public_urls"):
                result = self.middleware._process_health_probe(request)
        self.assertIsNone(result)
        self.assertEqual(request.urlconf, "config.public_urls")
        mock_conn.set_schema_to_public.assert_not_called()

    def test_health_path_returns_degraded_200_when_no_public_urlconf_and_db_fails(self):
        request = self.rf.get("/health/")
        exc = OperationalError("consuming input failed: SSL error: unexpected eof while reading")
        mock_conn = MagicMock()
        mock_conn.set_schema_to_public.side_effect = exc
        with patch("apps.schools.middleware_tenant_main.connection", mock_conn):
            with patch("django.conf.settings.PUBLIC_SCHEMA_URLCONF", None):
                response = self.middleware._process_health_probe(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Retry-After"], "30")
        import json

        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database"], "unavailable")

    def test_non_health_transient_db_returns_503(self):
        request = self.rf.get("/authentication/login/")
        exc = OperationalError(
            "consuming input failed: SSL error: unexpected eof while reading"
        )
        with patch.object(
            TenantMainMiddleware,
            "process_request",
            side_effect=exc,
        ):
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "30")
        self.assertIn(b"temporarily unavailable", response.content)

    def test_recovery_mode_on_super_returns_503(self):
        request = self.rf.get("/super/")
        exc = OperationalError(
            'connection failed: connection to server at "10.227.203.193", port 5432 failed: '
            "FATAL:  the database system is in recovery mode"
        )
        with patch.object(
            TenantMainMiddleware,
            "process_request",
            side_effect=exc,
        ):
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response["Retry-After"], "30")
        request = self.rf.get("/authentication/login/")
        try:
            from psycopg import OperationalError as PsycopgOperationalError
        except ImportError:
            self.skipTest("psycopg not installed")
        exc = PsycopgOperationalError(
            "consuming input failed: SSL error: unexpected eof while reading"
        )
        with patch.object(
            TenantMainMiddleware,
            "process_request",
            side_effect=exc,
        ):
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 503)

    def test_degraded_payload_shape(self):
        response = health_probe_degraded_response()
        self.assertEqual(response.status_code, 200)

    def test_transient_db_retries_once_before_503(self):
        request = self.rf.get("/authentication/login/")
        exc = OperationalError(
            "consuming input failed: SSL error: unexpected eof while reading"
        )
        with patch.object(
            TenantMainMiddleware,
            "process_request",
            side_effect=[exc, None],
        ):
            response = self.middleware.process_request(request)
        self.assertIsNone(response)
