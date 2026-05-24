"""Experience_control closure — marketplace catalog / install / monetization roster wires."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.tests.experience_control_registry import (
    EXPERIENCE_CONTROL_SCREENS,
    reverse_screen,
)

_MKT_IDS = frozenset(
    {
        "marketplace_catalog",
        "installed_apps",
        "marketplace_purchase_intent",
    }
)


class MarketplaceExperienceControlRegistryTests(SimpleTestCase):
    def test_marketplace_roster_entries_resolve(self):
        for row in EXPERIENCE_CONTROL_SCREENS:
            if row["id"] in _MKT_IDS:
                reverse_screen(row)
