"""Experience_control closure — governed query / analytics roster."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.tests.experience_control_registry import (
    EXPERIENCE_CONTROL_SCREENS,
    reverse_screen,
)


class AnalyticsExperienceControlRegistryTests(SimpleTestCase):
    def test_governed_query_builder_reverse(self):
        row = next(r for r in EXPERIENCE_CONTROL_SCREENS if r["id"] == "governed_query_builder")
        reverse_screen(row)
