"""Tests for the co-pilot ↔ governance-registry bridge (prototype)."""

from __future__ import annotations

from types import SimpleNamespace

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.studio_os.copilot_registry_insights import (
    _BACKLOG_SNAPSHOT_CACHE_KEY,
    build_registry_insights,
)


def _request(*, is_staff: bool):
    req = RequestFactory().get("/studio/copilot/rail/context/")
    req.user = SimpleNamespace(is_staff=is_staff, is_authenticated=True)
    return req


@override_settings(COPILOT_REGISTRY_INSIGHTS=True)
class CopilotRegistryInsightsTests(SimpleTestCase):
    def tearDown(self):
        cache.delete(_BACKLOG_SNAPSHOT_CACHE_KEY)

    def test_non_staff_gets_nothing(self):
        self.assertEqual(build_registry_insights(_request(is_staff=False)), [])

    def test_none_request_safe(self):
        self.assertEqual(build_registry_insights(None), [])

    @override_settings(COPILOT_REGISTRY_INSIGHTS=False)
    def test_disabled_returns_empty_even_for_staff(self):
        self.assertEqual(build_registry_insights(_request(is_staff=True)), [])

    def test_staff_gets_feature_gap_item(self):
        cache.delete(_BACKLOG_SNAPSHOT_CACHE_KEY)  # no backlog snapshot cached
        items = build_registry_insights(_request(is_staff=True))
        ids = {i["id"] for i in items}
        self.assertIn("registry-feature-gap", ids)
        # Backlog item is absent until an evaluation beat populates the cache —
        # the bridge must never run the gate scripts itself.
        self.assertNotIn("registry-backlog", ids)
        fg = next(i for i in items if i["id"] == "registry-feature-gap")
        self.assertEqual(fg["source"], "registry")
        self.assertIn("shipped", fg["body"])

    def test_backlog_item_appears_from_cached_snapshot(self):
        cache.set(
            _BACKLOG_SNAPSHOT_CACHE_KEY,
            {"summary": {"ready": 2, "ready_attention": 1, "waiting": 3, "blocked_external": 4}},
            60,
        )
        items = build_registry_insights(_request(is_staff=True))
        backlog = next((i for i in items if i["id"] == "registry-backlog"), None)
        self.assertIsNotNone(backlog)
        self.assertEqual(backlog["source"], "registry")
        for token in ("2 ready", "1 need review", "3 waiting", "4 blocked"):
            self.assertIn(token, backlog["body"])

    def test_malformed_cache_is_ignored(self):
        cache.set(_BACKLOG_SNAPSHOT_CACHE_KEY, "not-a-dict", 60)
        items = build_registry_insights(_request(is_staff=True))
        self.assertNotIn("registry-backlog", {i["id"] for i in items})
