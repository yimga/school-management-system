"""Adaptive admin landing: a still-onboarding school collapses the dense ops
dashboard to a focused setup surface; a configured school keeps the full ops
center. Pure-function tests of the decision + the hidden-module contract (the
flag-flipping itself reuses the existing backend_module_visibility template
gates, so no template render is needed here).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.accounts.views import (
    BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD,
    BACKEND_SETUP_LANDING_HIDDEN_MODULES,
    _resolve_setup_landing,
)


class ResolveSetupLandingTests(SimpleTestCase):
    def test_below_threshold_engages(self):
        self.assertTrue(_resolve_setup_landing(6, {}))
        self.assertTrue(
            _resolve_setup_landing(BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD - 1, {})
        )

    def test_at_or_above_threshold_does_not_engage(self):
        self.assertFalse(
            _resolve_setup_landing(BACKEND_SETUP_LANDING_DEFAULT_THRESHOLD, {})
        )
        self.assertFalse(_resolve_setup_landing(100, {}))

    def test_operator_can_disable_entirely(self):
        # Even a 0%% school stays on the full ops dashboard when disabled.
        self.assertFalse(
            _resolve_setup_landing(0, {"backend_adaptive_setup_landing": False})
        )

    def test_operator_can_tune_threshold(self):
        flags = {"backend_setup_landing_threshold": 30}
        self.assertTrue(_resolve_setup_landing(20, flags))
        self.assertFalse(_resolve_setup_landing(40, flags))

    def test_bad_percent_defaults_safely(self):
        # None / unparseable percent is treated as 0 -> still onboarding.
        self.assertTrue(_resolve_setup_landing(None, {}))
        self.assertTrue(_resolve_setup_landing("oops", {}))

    def test_has_launched_lifts_setup_landing_even_below_threshold(self):
        self.assertFalse(_resolve_setup_landing(10, {}, has_launched=True))

    def test_launch_ready_alone_keeps_setup_landing_for_golive_ceremony(self):
        self.assertTrue(_resolve_setup_landing(10, {}, launch_ready=True, has_launched=False))

    def test_setup_landing_when_not_launch_ready_and_low_percent(self):
        self.assertTrue(_resolve_setup_landing(10, {}, launch_ready=False))

    def test_hidden_modules_cover_the_dense_ops_widgets(self):
        # The setup surface must hide the heavy ops modules but is implemented by
        # flipping these specific backend_module_visibility keys.
        for key in ("overview", "welcome", "admin_portal", "planner"):
            self.assertIn(key, BACKEND_SETUP_LANDING_HIDDEN_MODULES)
