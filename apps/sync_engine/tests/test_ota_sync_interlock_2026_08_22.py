"""An out-of-date box tries to sync. Prove the code lane and the data lane interlock.

The failure this prevents is transactional split-brain: an appliance running last week's
code applying rows the cloud produced with this week's constraints, or the reverse. The
guarantee has three parts and each is asserted separately, because each can regress on
its own:

  * the cloud NOTICES, on a request the box was already making — no extra round trip, no
    second channel, no new port;
  * the box STOPS moving data while it is behind, and does so without losing ground —
    the cursors do not advance, so the held rows are re-offered in full afterwards;
  * the hold has an END. It expires, it is released when parity is reached, and it is
    never armed at all when this box has no way to act on it — because a school whose
    records stop syncing because a code update is pending is worse off than a school
    running one release behind.

``NoDatabaseInterlockTests`` runs with no test database at all (the repo's peer sessions
hold the shared one; see docs). ``HeldCycleIntegrationTests`` needs a database and proves
the end-to-end block/release on ``run_sync_cycle`` itself.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.sync_engine import upgrade_lock
from apps.sync_engine.cloud_endpoints import CLOUD_SYNC_PATHS
from apps.sync_engine.edge_outbox import (
    SYNC_MANIFEST_ADVICE_HEADER,
    SYNC_MANIFEST_HEADER,
    SYNC_MANIFEST_TARGET_HEADER,
    local_manifest_headers,
)


class _School:
    """Minimal stand-in: the lock only ever reads ``pk``."""

    def __init__(self, pk):
        self.pk = pk


def _manifest_file(hash_value: str) -> str:
    handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(
        {"manifest_hash": hash_value, "version_label": "test", "files": {"a.py": {"sha256": "x", "bytes": 1, "category": "APP_CORE"}}},
        handle,
    )
    handle.close()
    return handle.name


class UpgradeRouteContractTests(SimpleTestCase):
    """The OTA routes must be reachable at the paths a box will hardcode."""

    def test_pinned_upgrade_paths_equal_reverse(self):
        for name in ("api:sync-upgrade-manifest", "api:sync-upgrade-chunk"):
            with self.subTest(name=name):
                self.assertEqual(reverse(name), CLOUD_SYNC_PATHS[name])

    def test_upgrade_routes_sit_on_the_existing_sync_mount(self):
        """No second hostname, no second port: a school firewall approved one lane."""
        for name in ("api:sync-upgrade-manifest", "api:sync-upgrade-chunk"):
            self.assertTrue(
                reverse(name).startswith("/api/sync/"),
                f"{name} left the approved lane at {reverse(name)}",
            )


class NoDatabaseInterlockTests(SimpleTestCase):
    """The hold state machine and the cloud-side comparison. No database, no network."""

    def setUp(self):
        super().setUp()
        upgrade_lock.reset()
        self.school = _School(41)
        upgrade_lock.release(self.school)

    def tearDown(self):
        upgrade_lock.reset()
        upgrade_lock.release(self.school)
        super().tearDown()

    # ── the lock itself ──────────────────────────────────────────────────────
    def test_a_school_starts_active(self):
        self.assertEqual(upgrade_lock.state(self.school)["state"], upgrade_lock.SYNC_STATE_ACTIVE)
        self.assertFalse(upgrade_lock.is_held(self.school))

    def test_hold_then_release(self):
        upgrade_lock.hold(self.school, target_hash="a" * 64, current_hash="b" * 64)
        self.assertTrue(upgrade_lock.is_held(self.school))
        self.assertEqual(upgrade_lock.state(self.school)["target_hash"], "a" * 64)
        upgrade_lock.release(self.school)
        self.assertFalse(upgrade_lock.is_held(self.school))

    def test_re_holding_the_same_target_preserves_how_long_it_has_been_stuck(self):
        """Otherwise every poll resets the clock and a wedged box looks freshly held."""
        first = upgrade_lock.hold(self.school, target_hash="a" * 64)
        time.sleep(0.01)
        again = upgrade_lock.hold(self.school, target_hash="a" * 64)
        self.assertEqual(first["since"], again["since"])

    def test_a_new_target_restarts_the_clock(self):
        first = upgrade_lock.hold(self.school, target_hash="a" * 64)
        again = upgrade_lock.hold(self.school, target_hash="c" * 64)
        self.assertNotEqual(first["since"], again["since"])

    @override_settings(RMC_OTA_HOLD_TTL_SECONDS=900)
    def test_the_configured_ttl_is_honoured_above_the_floor(self):
        self.assertEqual(upgrade_lock.hold_ttl_seconds(), 900)

    @override_settings(RMC_OTA_HOLD_TTL_SECONDS=5)
    def test_the_ttl_has_a_floor_so_a_misconfig_cannot_make_the_hold_useless(self):
        """A one-second hold would lapse between the arm and the next tick, every time."""
        self.assertEqual(upgrade_lock.hold_ttl_seconds(), 60)

    def test_a_hold_is_written_with_an_expiry_so_a_failed_upgrade_cannot_mute_sync_forever(self):
        """The guarantee is that the cache entry EXPIRES, not how long the floor is.

        Patched rather than configured because the floor (correctly) refuses a TTL short
        enough to assert against in a test — and a test that sleeps for a minute to prove
        a one-line property is a test people delete.
        """
        with mock.patch.object(upgrade_lock, "hold_ttl_seconds", return_value=1):
            upgrade_lock.arm_local(target_hash="a" * 64)
            self.assertTrue(upgrade_lock.local_is_held())
            time.sleep(1.2)
            self.assertFalse(
                upgrade_lock.local_is_held(),
                "the hold outlived its TTL — a box whose upgrade failed at 2am would "
                "never sync again",
            )

    def test_acknowledgement_survives_a_disarm(self):
        """A target carried as far as the mode allows must stop re-blocking the rail."""
        upgrade_lock.arm_local(target_hash="a" * 64)
        upgrade_lock.acknowledge_local("a" * 64)
        upgrade_lock.disarm_local()
        self.assertFalse(upgrade_lock.local_is_held())
        self.assertEqual(upgrade_lock.acknowledged_target(), "a" * 64)

    # ── the cloud-side comparison ────────────────────────────────────────────
    def test_handshake_is_silent_when_the_box_declares_nothing(self):
        """An older appliance must keep working exactly as it did before this existed."""
        from apps.api.sync_bundle_api import _manifest_handshake

        request = RequestFactory().get("/api/sync/bundle/download/")
        self.assertEqual(_manifest_handshake(request, self.school), ("", ""))
        self.assertFalse(upgrade_lock.is_held(self.school))

    def test_handshake_holds_when_the_manifests_differ(self):
        from apps.api.sync_bundle_api import _manifest_handshake

        cloud = _manifest_file("c" * 64)
        request = RequestFactory().get(
            "/api/sync/bundle/download/",
            **{"HTTP_" + SYNC_MANIFEST_HEADER.upper().replace("-", "_"): "b" * 64},
        )
        with override_settings(RMC_OTA_MANIFEST_PATH=cloud):
            target, advice = _manifest_handshake(request, self.school)

        self.assertEqual(target, "c" * 64)
        self.assertIn("upgrade available", advice)
        self.assertTrue(upgrade_lock.is_held(self.school))

    def test_handshake_releases_when_the_manifests_agree(self):
        from apps.api.sync_bundle_api import _manifest_handshake

        cloud = _manifest_file("c" * 64)
        upgrade_lock.hold(self.school, target_hash="c" * 64)
        request = RequestFactory().get(
            "/api/sync/bundle/download/",
            **{"HTTP_" + SYNC_MANIFEST_HEADER.upper().replace("-", "_"): "c" * 64},
        )
        with override_settings(RMC_OTA_MANIFEST_PATH=cloud):
            target, advice = _manifest_handshake(request, self.school)

        self.assertEqual((target, advice), ("", ""))
        self.assertFalse(
            upgrade_lock.is_held(self.school),
            "reaching parity must release the rail on the very same request",
        )

    def test_handshake_is_silent_when_the_cloud_has_no_manifest(self):
        """An operator that never generated one must not hold every box on the platform."""
        from apps.api.sync_bundle_api import _manifest_handshake

        empty = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        empty.write("{}")
        empty.close()
        request = RequestFactory().get(
            "/api/sync/bundle/download/",
            **{"HTTP_" + SYNC_MANIFEST_HEADER.upper().replace("-", "_"): "b" * 64},
        )
        with override_settings(RMC_OTA_MANIFEST_PATH=empty.name):
            self.assertEqual(_manifest_handshake(request, self.school), ("", ""))
        self.assertFalse(upgrade_lock.is_held(self.school))

    # ── the box-side declaration ─────────────────────────────────────────────
    def test_box_declares_its_manifest_on_the_existing_rail(self):
        local = _manifest_file("b" * 64)
        with override_settings(RMC_OTA_MANIFEST_PATH=local):
            headers = local_manifest_headers()
        self.assertEqual(headers.get(SYNC_MANIFEST_HEADER), "b" * 64)

    def test_a_box_with_no_manifest_declares_nothing_rather_than_lying(self):
        with override_settings(RMC_OTA_MANIFEST_PATH=str(Path(tempfile.gettempdir()) / "rmc-absent.json")):
            headers = local_manifest_headers()
        self.assertNotIn(SYNC_MANIFEST_HEADER, headers)

    def test_response_header_names_are_distinct(self):
        """A typo that collided two headers would silently disable the interlock."""
        self.assertNotEqual(SYNC_MANIFEST_HEADER, SYNC_MANIFEST_TARGET_HEADER)
        self.assertNotEqual(SYNC_MANIFEST_TARGET_HEADER, SYNC_MANIFEST_ADVICE_HEADER)


class HeldCycleIntegrationTests(TestCase):
    """The whole point, end to end: blocked while behind, moving again once upgraded."""

    def setUp(self):
        super().setUp()
        upgrade_lock.reset()
        from apps.schools.models import School

        self.school = School.objects.create(name="Interlock Test School", slug="interlock-test")

    def tearDown(self):
        upgrade_lock.reset()
        super().tearDown()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://operator.invalid")
    def test_a_held_box_moves_no_data_and_says_why(self):
        from apps.sync_engine.models import EdgeSyncCursor, EdgeSyncRun
        from apps.sync_engine.sync_runner import run_sync_cycle

        upgrade_lock.arm_local(target_hash="c" * 64, reason="upgrade available")
        result = run_sync_cycle(self.school, mode="live")

        self.assertTrue(result["held_for_upgrade"])
        self.assertEqual(result["upgrade_target"], "c" * 64)
        self.assertEqual(result["pushed"], 0)
        self.assertEqual(result["pulled"], 0)
        self.assertTrue(
            result["ok"],
            "a held cycle is the system working; reporting it as an error trains "
            "operators to ignore red rows during every upgrade window",
        )
        self.assertIn("held for upgrade", result["message"])

        # Exactly one run row, and no ground was given up.
        self.assertEqual(EdgeSyncRun.objects.filter(school=self.school).count(), 1)
        self.assertFalse(
            EdgeSyncCursor.objects.filter(school=self.school).exists(),
            "a hold must defer work, never advance a cursor over ground that never moved",
        )

    @override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://operator.invalid")
    def test_a_dry_probe_is_exempt_so_an_operator_can_still_diagnose(self):
        from apps.sync_engine.sync_runner import run_sync_cycle

        upgrade_lock.arm_local(target_hash="c" * 64)
        result = run_sync_cycle(self.school, mode="dry")
        self.assertFalse(
            result["held_for_upgrade"],
            "a no-write probe writes nothing in either direction; refusing it would "
            "remove the one tool that answers 'can this box still reach the cloud'",
        )

    @override_settings(RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://operator.invalid")
    def test_once_the_upgrade_is_applied_the_cycle_runs_again(self):
        """The release half. Without it the block is an outage, not an interlock."""
        from apps.sync_engine.sync_runner import run_sync_cycle

        upgrade_lock.arm_local(target_hash="c" * 64)
        self.assertTrue(run_sync_cycle(self.school, mode="live")["held_for_upgrade"])

        # What LocalRuntimeUpgradeManager does on success.
        upgrade_lock.acknowledge_local("c" * 64)
        upgrade_lock.disarm_local()

        result = run_sync_cycle(self.school, mode="live")
        self.assertFalse(result["held_for_upgrade"])
        # The operator base is unreachable in a test, so the cycle reports a transport
        # failure — which is the proof that matters here: it got as far as the network
        # instead of stopping at the interlock.
        self.assertNotIn("held for upgrade", result["message"])
