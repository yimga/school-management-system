"""Unit tests for fleet wall SSE payload builder."""
from __future__ import annotations

from django.test import RequestFactory, TestCase

from apps.schools.fleet_live_payload import row_revision_map
from apps.schools.fleet_wall_payload import (
    build_fleet_wall_context,
    build_fleet_wall_rows,
    iter_fleet_wall_sse_events,
    merge_wall_row_revisions,
    request_is_fleet_wall_mode,
)
from apps.schools.models import School


class FleetWallPayloadTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Fleet Wall School",
            slug="fleet-wall-school",
            subdomain="fleet-wall-school",
            is_active=True,
            is_approved=True,
        )

    def test_request_is_fleet_wall_mode(self):
        request = RequestFactory().get("/super/api/fleet/stream/?mode=wall")
        self.assertTrue(request_is_fleet_wall_mode(request))
        self.assertFalse(request_is_fleet_wall_mode(RequestFactory().get("/super/api/fleet/stream/")))

    def test_bootstrap_emits_summary_chunks_and_ready(self):
        request = RequestFactory().get("/super/api/fleet/stream/?mode=wall&chunk_size=25")
        events = iter_fleet_wall_sse_events(
            request,
            since_revision=None,
            since_row_revisions=None,
            wall_bootstrapped=False,
        )
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "summary")
        self.assertIn("chunk", types)
        self.assertEqual(types[-1], "wall_ready")
        self.assertGreaterEqual(len(events[1]["rows"]), 1)

    def test_delta_after_bootstrap_only_returns_changed_rows(self):
        request = RequestFactory().get("/super/api/fleet/stream/?mode=wall&chunk_size=25")
        bootstrap = iter_fleet_wall_sse_events(
            request,
            since_revision=None,
            since_row_revisions=None,
            wall_bootstrapped=False,
        )
        row_map = {}
        for event in bootstrap:
            if event.get("type") == "chunk":
                row_map.update(row_revision_map(event.get("rows") or []))

        row = bootstrap[1]["rows"][0]
        stale_map = dict(row_map)
        stale_map[row["id"]] = "deadbeef0000"

        events = iter_fleet_wall_sse_events(
            request,
            since_revision="0000000000000000",
            since_row_revisions=stale_map,
            wall_bootstrapped=True,
        )
        self.assertEqual(events[0]["type"], "summary")
        self.assertEqual(events[1]["type"], "delta")
        self.assertEqual(len(events[1]["changed_rows"]), 1)
        self.assertEqual(events[1]["changed_rows"][0]["id"], row["id"])

    def test_unchanged_when_revision_matches_after_bootstrap(self):
        request = RequestFactory().get("/super/api/fleet/stream/?mode=wall")
        ctx = build_fleet_wall_context()
        events = iter_fleet_wall_sse_events(
            request,
            since_revision=ctx["revision"],
            since_row_revisions=row_revision_map(build_fleet_wall_rows()),
            wall_bootstrapped=True,
        )
        self.assertEqual(events[0]["type"], "unchanged")

    def test_merge_wall_row_revisions_updates_map(self):
        rows = build_fleet_wall_rows()
        merged = merge_wall_row_revisions({}, [{"type": "chunk", "rows": rows[:1]}])
        self.assertIn(rows[0]["id"], merged)
