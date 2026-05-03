"""Experience_control closure — finance dashboard + payment readiness roster."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.tests.experience_control_registry import (
    EXPERIENCE_CONTROL_SCREENS,
    reverse_screen,
)


class FinanceExperienceControlRegistryTests(SimpleTestCase):
    def test_finance_roster_entries_resolve(self):
        for key in ("finance_dashboard", "payment_readiness_setup"):
            row = next(r for r in EXPERIENCE_CONTROL_SCREENS if r["id"] == key)
            reverse_screen(row)
