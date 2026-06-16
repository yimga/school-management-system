"""_enable_offline_mode_policy_module must report enabled-state, not change-flag.

Regression: returned False when offline_mode was already on; the caller stores
the return as result['offline_mode_module_enabled'], so an already-enabled school
wrongly reported the module as NOT enabled.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime.offline_mode_bundle import (
    _enable_offline_mode_policy_module,
)


class _School:
    def __init__(self, features):
        self.features = features


class OfflineModeEnableReturnTests(SimpleTestCase):
    def test_already_enabled_reports_true(self):
        # No DB touched: the already-enabled branch returns before any save().
        school = _School({"offline_mode": True})
        self.assertTrue(_enable_offline_mode_policy_module(school))

    def test_dry_run_when_disabled_reports_true(self):
        school = _School({})
        self.assertTrue(_enable_offline_mode_policy_module(school, dry_run=True))
        # dry-run must not mutate.
        self.assertFalse(school.features.get("offline_mode"))
