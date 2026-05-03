"""Experience_control closure — event console roster wiring."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.tests.experience_control_registry import (
    EXPERIENCE_CONTROL_SCREENS,
    reverse_screen,
)


class EventsExperienceControlRegistryTests(SimpleTestCase):
    def test_event_console_reverse(self):
        row = next(r for r in EXPERIENCE_CONTROL_SCREENS if r["id"] == "event_console")
        reverse_screen(row)
