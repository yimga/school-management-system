"""Batch 1518 — public status real probes and incidents."""

from __future__ import annotations

import os
from unittest import mock

from django.test import Client, TestCase, override_settings

from apps.observability.platform_status_incident import PlatformStatusIncident
from apps.observability.public_status import (
    _probe_auth,
    _probe_celery_queue_depth,
    _probe_database,
    _probe_parent_finance_health,
    build_public_status_payload,
    enrollment_peak_mode_enabled,
)


class PublicStatusProbeTests(TestCase):
    def test_database_probe_returns_tuple(self):
        state, detail = _probe_database()
        self.assertIn(state, ("operational", "degraded", "outage"))
        self.assertTrue(detail)

    def test_auth_probe_operational(self):
        state, _ = _probe_auth()
        self.assertIn(state, ("operational", "degraded"))

    def test_parent_finance_health_probe(self):
        state, _ = _probe_parent_finance_health()
        self.assertIn(state, ("operational", "degraded"))

    def test_celery_probe_best_effort(self):
        state, _ = _probe_celery_queue_depth()
        self.assertIn(state, ("operational", "degraded"))

    def test_payload_includes_components_and_incidents(self):
        payload = build_public_status_payload()
        self.assertIn("components", payload)
        self.assertGreaterEqual(len(payload["components"]), 5)
        self.assertIn("incidents", payload)
        keys = {row["key"] for row in payload["components"]}
        self.assertIn("payments", keys)
        self.assertIn("auth", keys)

    def test_public_incident_serialized(self):
        PlatformStatusIncident.objects.create(
            title="Payments delay",
            summary="Investigating elevated latency on fee checkout.",
            status=PlatformStatusIncident.Status.INVESTIGATING,
            severity=PlatformStatusIncident.Severity.HIGH,
            component_keys=["payments"],
        )
        payload = build_public_status_payload()
        self.assertEqual(len(payload["incidents"]), 1)
        self.assertEqual(payload["incidents"][0]["title"], "Payments delay")

    @override_settings(ENROLLMENT_PEAK_MODE="1")
    def test_enrollment_peak_banner_in_payload(self):
        with mock.patch.dict(os.environ, {"ENROLLMENT_PEAK_MODE": "1"}):
            self.assertTrue(enrollment_peak_mode_enabled())
        payload = build_public_status_payload()
        self.assertTrue(payload.get("enrollment_peak_mode"))
        self.assertTrue(payload.get("enrollment_peak_banner"))


class PublicStatusViewTests(TestCase):
    def test_status_json_endpoint(self):
        client = Client()
        resp = client.get("/status/", HTTP_ACCEPT="application/json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("overall_status", data)
        self.assertIn("components", data)
