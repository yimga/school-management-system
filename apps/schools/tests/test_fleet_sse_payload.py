"""Unit tests for fleet SSE payload builder."""
from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.schools.fleet_live_payload import build_fleet_sse_payload
from apps.schools.models import School


class FleetSsePayloadTests(TestCase):
    def setUp(self):
        School.objects.create(
            name="Fleet SSE School",
            slug="fleet-sse-school",
            subdomain="fleet-sse-school",
            is_active=True,
            is_approved=True,
        )

    def test_summary_only_when_no_page_params(self):
        request = RequestFactory().get("/super/api/fleet/stream/")
        payload = build_fleet_sse_payload(request)
        self.assertIn("summary", payload)
        self.assertIn("revision", payload)
        self.assertNotIn("rows", payload)

    def test_includes_paginated_rows_when_page_requested(self):
        request = RequestFactory().get(
            "/super/api/fleet/stream/?page=1&page_size=25&include_rows=1"
        )
        payload = build_fleet_sse_payload(request)
        self.assertIn("rows", payload)
        self.assertGreaterEqual(len(payload["rows"]), 1)
        self.assertIn("pagination", payload)
        self.assertEqual(payload["pagination"]["page"], 1)
        self.assertEqual(payload["pagination"]["page_size"], 25)
