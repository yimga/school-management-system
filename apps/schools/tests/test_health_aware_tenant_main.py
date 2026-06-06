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

    def test_health_path_returns_degraded_200_on_transient_db(self):
        request = self.rf.get("/health/")
        exc = OperationalError("consuming input failed: SSL error: unexpected eof while reading")
        mock_conn = MagicMock()
        mock_conn.set_schema_to_public.side_effect = exc
        with patch("apps.schools.middleware_tenant_main.connection", mock_conn):
            response = self.middleware._process_health_probe(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Retry-After"], "30")
        import json

        payload = json.loads(response.content)
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["database"], "unavailable")

    def test_non_health_transient_db_still_raises(self):
        request = self.rf.get("/super/")
        exc = OperationalError("consuming input failed: SSL error: unexpected eof while reading")
        with patch.object(
            TenantMainMiddleware,
            "process_request",
            side_effect=exc,
        ):
            with self.assertRaises(OperationalError):
                self.middleware.process_request(request)

    def test_degraded_payload_shape(self):
        response = health_probe_degraded_response()
        self.assertEqual(response.status_code, 200)
