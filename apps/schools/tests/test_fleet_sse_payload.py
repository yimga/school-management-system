"""Unit tests for fleet SSE payload builder."""
from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.schools.fleet_live_payload import (
    build_fleet_sse_payload,
    fleet_row_revision,
    row_revision_map,
)
from apps.schools.models import School


class FleetSsePayloadTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
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
        self.assertTrue(payload.get("snapshot"))
        self.assertIn("rows", payload)
        self.assertGreaterEqual(len(payload["rows"]), 1)
        self.assertIn("row_revision", payload["rows"][0])
        self.assertIn("pagination", payload)
        self.assertEqual(payload["pagination"]["page"], 1)
        self.assertEqual(payload["pagination"]["page_size"], 25)

    def test_unchanged_when_since_revision_matches(self):
        request = RequestFactory().get(
            "/super/api/fleet/stream/?page=1&page_size=25&include_rows=1"
        )
        full = build_fleet_sse_payload(request)
        revision = full["revision"]
        since_request = RequestFactory().get(
            f"/super/api/fleet/stream/?page=1&page_size=25&include_rows=1&since_revision={revision}"
        )
        payload = build_fleet_sse_payload(since_request, since_revision=revision)
        self.assertTrue(payload.get("unchanged"))
        self.assertNotIn("rows", payload)
        self.assertEqual(payload["revision"], revision)

    def test_delta_emits_only_changed_rows(self):
        request = RequestFactory().get(
            "/super/api/fleet/stream/?page=1&page_size=25&include_rows=1"
        )
        snapshot = build_fleet_sse_payload(request)
        row = snapshot["rows"][0]
        row_map = row_revision_map(snapshot["rows"])
        stale_map = dict(row_map)
        stale_map[row["id"]] = "deadbeef0000"

        delta = build_fleet_sse_payload(
            request,
            since_revision="0000000000000000",
            since_row_revisions=stale_map,
        )
        self.assertTrue(delta.get("delta"))
        self.assertNotIn("rows", delta)
        self.assertEqual(len(delta.get("changed_rows") or []), 1)
        self.assertEqual(delta["changed_rows"][0]["id"], row["id"])

    def test_delta_empty_when_page_rows_unchanged(self):
        request = RequestFactory().get(
            "/super/api/fleet/stream/?page=1&page_size=25&include_rows=1"
        )
        snapshot = build_fleet_sse_payload(request)
        row_map = row_revision_map(snapshot["rows"])

        delta = build_fleet_sse_payload(
            request,
            since_revision="0000000000000000",
            since_row_revisions=row_map,
        )
        self.assertTrue(delta.get("delta"))
        self.assertEqual(delta.get("changed_rows"), [])

    def test_fleet_row_revision_stable(self):
        row = {
            "id": "1",
            "fleet_state": "live",
            "heatmap_tier": "healthy",
            "roster_state": "healthy",
            "is_active": True,
            "is_approved": True,
            "is_frozen": False,
            "lifecycle_state": "active",
        }
        self.assertEqual(fleet_row_revision(row), fleet_row_revision(row))
