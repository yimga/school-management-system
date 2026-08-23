"""The default lane must upgrade a school WITHOUT ever pausing its data sync.

RMC_OTA_AUTO_APPLY defaults to "assets" so the pipeline is not ceremonial — a box that
only ever reports drift and waits for a hand that must reach every school individually
is a pipeline nobody uses. But making it the default is only safe if the assets lane
never arms the sync hold, and that is a separate decision from applying assets:

  * the hold exists because the DATABASE may be mid-migration;
  * an assets lane carries no migration and no importable python, by construction —
    ASSET_CATEGORIES cannot contain a .py file, because categorise() returns APP_CORE
    for .py before the fall-through;
  * so there is no schema to be mid-anything, and holding a school's records to deliver
    a stylesheet is pure cost with no safety bought.

The skew case that DOES need care is already handled precisely one layer up: the cloud's
_schema_handshake withholds exactly the entities owned by an app the box is behind on and
lets everything else through, rather than stopping the cycle.

These are DB-free: they are decisions about settings and categories.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.sync_engine import local_upgrade
from apps.sync_engine.system_manifest import (
    APP_CORE,
    ASSET_CATEGORIES,
    CONFIG,
    MIGRATION,
)


class DefaultLaneTests(SimpleTestCase):
    def test_the_shipped_default_is_assets_not_off(self):
        """"off" made the whole pipeline ceremonial: nothing upgraded unless asked."""
        self.assertEqual(local_upgrade.auto_apply_mode(), local_upgrade.MODE_ASSETS)

    @override_settings(RMC_OTA_AUTO_APPLY="off")
    def test_off_is_still_honoured_when_asked_for(self):
        self.assertEqual(local_upgrade.auto_apply_mode(), local_upgrade.MODE_OFF)

    @override_settings(RMC_OTA_AUTO_APPLY="full")
    def test_full_is_opt_in(self):
        self.assertEqual(local_upgrade.auto_apply_mode(), local_upgrade.MODE_FULL)

    @override_settings(RMC_OTA_AUTO_APPLY="nonsense")
    def test_an_unreadable_mode_does_not_silently_become_full(self):
        """A typo in an env var must never widen what the box is allowed to do."""
        self.assertNotEqual(local_upgrade.auto_apply_mode(), local_upgrade.MODE_FULL)


class AssetLaneCannotSplitBrainTests(SimpleTestCase):
    """Why the assets default is safe to ship, stated as a property rather than a claim."""

    def test_the_asset_lane_can_never_carry_python(self):
        self.assertNotIn(APP_CORE, ASSET_CATEGORIES)

    def test_the_asset_lane_can_never_carry_a_migration(self):
        self.assertNotIn(MIGRATION, ASSET_CATEGORIES)

    def test_the_asset_lane_can_never_carry_settings_or_deploy_descriptors(self):
        """CONFIG holds settings.py and urls.py — swapping those needs a reload."""
        self.assertNotIn(CONFIG, ASSET_CATEGORIES)


class HoldIsArmedOnlyForTheFullLaneTests(SimpleTestCase):
    """The sync hold pauses a school's records. It must be spent only where it buys safety.

    This reads the runner's arming condition directly rather than driving a whole cycle,
    because the property under test is exactly one boolean: which modes arm.
    """

    def _arming_condition(self, mode: str, target: str, acknowledged: str) -> bool:
        # Mirrors apps/sync_engine/sync_runner.py's arming guard. If that guard changes
        # shape, test_the_runner_still_guards_on_mode_full below fails and points here.
        return mode == local_upgrade.MODE_FULL and target != acknowledged

    def test_assets_mode_does_not_arm_the_hold(self):
        self.assertFalse(
            self._arming_condition(local_upgrade.MODE_ASSETS, "a" * 64, ""),
            "the assets lane armed the sync hold — a school's records would stop moving "
            "to deliver a stylesheet, and the default lane would be an outage",
        )

    def test_off_mode_does_not_arm_the_hold(self):
        self.assertFalse(self._arming_condition(local_upgrade.MODE_OFF, "a" * 64, ""))

    def test_full_mode_does_arm_the_hold(self):
        """Calibration: without this, the tests above pass by never arming at all."""
        self.assertTrue(self._arming_condition(local_upgrade.MODE_FULL, "a" * 64, ""))

    def test_an_acknowledged_target_stops_arming_even_in_full_mode(self):
        """Re-holding for something the box cannot finish is a permanent outage."""
        self.assertFalse(self._arming_condition(local_upgrade.MODE_FULL, "a" * 64, "a" * 64))

    def test_the_runner_still_guards_on_mode_full(self):
        """Pins the source, so the mirror above cannot drift away from the real guard."""
        import inspect

        from apps.sync_engine import sync_runner

        source = inspect.getsource(sync_runner)
        self.assertIn(
            "local_upgrade.auto_apply_mode() == local_upgrade.MODE_FULL",
            source,
            "the runner's arming guard changed shape; if the hold is now armed for a "
            "lane that carries no migration, a school's data sync pauses for nothing",
        )
        self.assertNotIn(
            "local_upgrade.auto_apply_mode() != local_upgrade.MODE_OFF",
            source,
            "the runner reverted to arming the hold for ANY non-off mode, which makes "
            "the assets default pause data sync on every template change",
        )
