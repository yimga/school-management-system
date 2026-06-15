"""Seals for the fleet poller cache (rmc:fleet:status:v1).

The cockpit live poll hits build_fleet_live_payload(include_rows=False) every
~15s from every operator tab. Caching the request-invariant full-fleet payload
collapses that storm to one compute per poll window. These tests pin:
  * the hot path (no q, no rows) is cached under the canonical key;
  * a cached read re-stamps generated_at (timestamp stays honest);
  * the search / row-page path is NOT cached (operators browsing see fresh data);
  * invalidate_fleet_status_cache() busts it;
  * an operator lifecycle action busts it (immediate heatmap feedback).
"""
from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase

from apps.schools.control_plane_lifecycle import apply_school_lifecycle_action
from apps.schools.fleet_live_payload import build_fleet_live_payload
from apps.schools.fleet_status import (
    FLEET_STATUS_CACHE_KEY,
    invalidate_fleet_status_cache,
)
from apps.schools.models import School


class FleetPollerCacheTests(TestCase):
    def setUp(self):
        cache.delete(FLEET_STATUS_CACHE_KEY)

    def _school(self, n: int):
        return School.objects.create(
            name=f"Cache School {n}",
            slug=f"cache-school-{n}",
            subdomain=f"cache-school-{n}",
            is_active=True,
            is_approved=True,
        )

    def test_hot_path_populates_canonical_cache_key(self):
        self._school(1)
        self.assertIsNone(cache.get(FLEET_STATUS_CACHE_KEY))
        payload = build_fleet_live_payload(include_rows=False)
        self.assertIsNotNone(cache.get(FLEET_STATUS_CACHE_KEY))
        self.assertEqual(payload["rows"], [])

    def test_cached_read_serves_stale_until_invalidated(self):
        self._school(1)
        first = build_fleet_live_payload(include_rows=False)
        first_total = first["pagination"]["total"]

        # Mutate state WITHOUT invalidating — a cache hit must still serve the
        # prior snapshot (proves we read the cache, not recompute every call).
        self._school(2)
        cached = build_fleet_live_payload(include_rows=False)
        self.assertEqual(cached["pagination"]["total"], first_total)
        self.assertEqual(cached["revision"], first["revision"])

        # Invalidate → next compute reflects the new school.
        invalidate_fleet_status_cache()
        fresh = build_fleet_live_payload(include_rows=False)
        self.assertEqual(fresh["pagination"]["total"], first_total + 1)

    def test_cached_read_restamps_generated_at(self):
        self._school(1)
        first = build_fleet_live_payload(include_rows=False)
        second = build_fleet_live_payload(include_rows=False)
        # Same cached body (same revision) but a freshly stamped timestamp.
        self.assertEqual(second["revision"], first["revision"])
        self.assertGreaterEqual(second["generated_at"], first["generated_at"])

    def test_search_path_is_not_cached(self):
        self._school(1)
        build_fleet_live_payload(q="cache", include_rows=True)
        self.assertIsNone(cache.get(FLEET_STATUS_CACHE_KEY))

    def test_row_page_path_is_not_cached(self):
        self._school(1)
        build_fleet_live_payload(page=1, page_size=50, include_rows=True)
        self.assertIsNone(cache.get(FLEET_STATUS_CACHE_KEY))

    def test_lifecycle_action_busts_cache(self):
        school = self._school(1)
        build_fleet_live_payload(include_rows=False)
        self.assertIsNotNone(cache.get(FLEET_STATUS_CACHE_KEY))
        apply_school_lifecycle_action(school, action="freeze", reason="STORAGE")
        self.assertIsNone(cache.get(FLEET_STATUS_CACHE_KEY))
