"""Not every school can afford the box the spec sheet assumes.

The release layout buys atomic code swaps by keeping whole trees side by side. That is a
fine trade on a box with room and a terrible one on a small appliance, because the failure
is not "the upgrade did not apply" -- it is a full filesystem, which stops Postgres
writing, and the school loses its data sync, its portal and its offline shell along with
the upgrade it never wanted that badly.

So every path that copies a tree has to answer two questions first: is there room, and if
something goes wrong halfway, can the box still serve? These tests pin the answers.

The app tree measured 2026-08-22 is ~496MB across 16333 files, so a box on this layout is
committing roughly a gigabyte to hold two releases. That number is why the guard exists,
and why nothing here is opt-out.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from collections import namedtuple
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.sync_engine import local_upgrade

REPO = Path(__file__).resolve().parents[3]

# shutil.disk_usage returns a namedtuple, and the code under test reads `.free`; a bare
# tuple here would pass the mock and fail the attribute, testing nothing.
_Usage = namedtuple("_Usage", "total used free")


class HeadroomSettingTests(SimpleTestCase):
    @override_settings(RMC_OTA_RELEASE_HEADROOM_PCT=140)
    def test_the_default_asks_for_more_than_the_tree_itself(self):
        """Exactly one tree of room means finishing the copy with zero bytes spare."""
        self.assertGreater(local_upgrade.release_headroom_ratio(), 1.0)

    @override_settings(RMC_OTA_RELEASE_HEADROOM_PCT=50)
    def test_headroom_can_never_be_set_below_the_tree_size(self):
        """A box must not be able to opt into a copy that provably does not fit."""
        self.assertGreaterEqual(local_upgrade.release_headroom_ratio(), 1.0)

    @override_settings(RMC_OTA_RELEASE_HEADROOM_PCT="not a number")
    def test_a_junk_value_falls_back_instead_of_crashing_the_box(self):
        self.assertGreaterEqual(local_upgrade.release_headroom_ratio(), 1.0)

    @override_settings(RMC_OTA_RELEASES_KEPT=1)
    def test_pruning_can_never_be_told_to_destroy_the_rollback_target(self):
        """Keeping one release means the box cannot go back, which is the whole point."""
        self.assertGreaterEqual(local_upgrade.releases_to_keep(), 2)


class TreeMeasurementTests(SimpleTestCase):
    def test_a_tree_is_measured_not_guessed(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "sub").mkdir()
            (root / "a.txt").write_bytes(b"x" * 1000)
            (root / "sub" / "b.txt").write_bytes(b"y" * 2000)
            self.assertGreaterEqual(local_upgrade.tree_bytes(root), 3000)

    def test_an_unreadable_tree_measures_zero_rather_than_raising(self):
        self.assertEqual(local_upgrade.tree_bytes(Path("does-not-exist-anywhere")), 0)


class RefusalTests(SimpleTestCase):
    """A box that refuses an upgrade keeps syncing. A box with a full disk does not."""

    def setUp(self):
        super().setUp()
        self.manager = local_upgrade.LocalRuntimeUpgradeManager.__new__(
            local_upgrade.LocalRuntimeUpgradeManager
        )
        self.manager._say = lambda *a, **k: None

    @override_settings(RMC_OTA_RELEASE_HEADROOM_PCT=140)
    def test_a_small_disk_refuses_the_swap(self):
        with mock.patch.object(
            local_upgrade, "tree_bytes", return_value=500 * 1024 * 1024
        ), mock.patch.object(
            shutil, "disk_usage", return_value=_Usage(0, 0, 200 * 1024 * 1024)
        ):
            with self.assertRaises(local_upgrade.UpgradeAborted) as caught:
                self.manager._require_disk_headroom(Path("."), Path("."))
        message = str(caught.exception)
        self.assertIn("not enough disk", message)
        self.assertIn(
            "keeps syncing", message, "the message must say the box is still alive"
        )
        self.assertIn(
            "RMC_OTA_RELEASE_ROOT",
            message,
            "and it must say what an operator can actually do about it",
        )

    @override_settings(RMC_OTA_RELEASE_HEADROOM_PCT=140)
    def test_a_roomy_disk_proceeds(self):
        """Calibration: without this, "it refuses" proves nothing."""
        with mock.patch.object(
            local_upgrade, "tree_bytes", return_value=100 * 1024 * 1024
        ), mock.patch.object(
            shutil, "disk_usage", return_value=_Usage(0, 0, 900 * 1024 * 1024)
        ):
            self.manager._require_disk_headroom(Path("."), Path("."))  # must not raise

    def test_an_unmeasurable_disk_does_not_block_the_upgrade(self):
        """Refusing on "I could not tell" would strand every box with an odd filesystem."""
        with mock.patch.object(
            local_upgrade, "tree_bytes", side_effect=OSError("cannot stat")
        ):
            self.manager._require_disk_headroom(Path("."), Path("."))  # must not raise


class PruningTests(SimpleTestCase):
    """Every upgrade adds a whole tree. Something has to remove one."""

    def setUp(self):
        super().setUp()
        self.manager = local_upgrade.LocalRuntimeUpgradeManager.__new__(
            local_upgrade.LocalRuntimeUpgradeManager
        )
        self.manager._say = lambda *a, **k: None

    def _releases(self, tmp, names):
        releases = Path(tmp) / "releases"
        releases.mkdir(parents=True)
        made = []
        for index, name in enumerate(names):
            directory = releases / name
            directory.mkdir()
            (directory / "marker").write_text(name, encoding="utf-8")
            stamp = 1_000_000 + index * 100
            os.utime(directory, (stamp, stamp))
            made.append(directory)
        return releases, made

    @override_settings(RMC_OTA_RELEASES_KEPT=2)
    def test_old_releases_are_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            releases, made = self._releases(tmp, ["r1", "r2", "r3", "r4", "r5"])
            current, previous = made[-1], made[-2]
            self.manager._prune_old_releases(releases, keep=[current, previous])
            self.assertTrue(current.is_dir(), "the running release was deleted")
            self.assertTrue(previous.is_dir(), "the rollback target was deleted")
            self.assertFalse(made[0].is_dir(), "an ancient release survived the prune")

    @override_settings(RMC_OTA_RELEASES_KEPT=2)
    def test_the_running_release_and_the_rollback_target_always_survive(self):
        with tempfile.TemporaryDirectory() as tmp:
            releases, made = self._releases(tmp, ["r1", "r2"])
            self.manager._prune_old_releases(releases, keep=[made[1], made[0]])
            self.assertTrue(made[0].is_dir())
            self.assertTrue(made[1].is_dir())

    def test_pruning_a_missing_directory_is_not_an_error(self):
        """This runs straight after a successful flip; it must never undo one."""
        self.manager._prune_old_releases(Path("no-such-releases-dir"), keep=[])

    def test_a_none_in_the_keep_list_is_survivable(self):
        """There is no rollback target on the very first upgrade."""
        with tempfile.TemporaryDirectory() as tmp:
            releases, made = self._releases(tmp, ["r1"])
            self.manager._prune_old_releases(releases, keep=[made[0], None])
            self.assertTrue(made[0].is_dir())


class BootNeverFailsTests(SimpleTestCase):
    """The boot script's contract, read from the script itself.

    A school whose box does not start is in far more trouble than one whose box needs an
    image rebuild to take a code upgrade -- and the boxes most likely to hit a short disk
    are the cheap ones, belonging to the schools least able to absorb an outage.
    """

    def setUp(self):
        super().setUp()
        self.script = (REPO / "deploy/selfhost/release_layout.sh").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_it_checks_free_space_before_copying_a_tree(self):
        self.assertIn("df -Pk", self.script)
        self.assertIn("du -sk", self.script)
        self.assertIn("RMC_OTA_RELEASE_HEADROOM_PCT", self.script)

    def test_every_failure_path_falls_back_to_the_live_tree(self):
        """Four ways to fail; four ways to still boot."""
        self.assertGreaterEqual(
            self.script.count('echo "${live}"'),
            4,
            "a failure path does not fall back to the live tree, so a box that cannot "
            "seed a release would fail to start at all",
        )

    def test_a_partial_copy_can_never_be_mistaken_for_a_release(self):
        self.assertIn(".partial", self.script)

    def test_it_uses_posix_flags_so_it_runs_on_a_busybox_image(self):
        """A cheap ARM box is likely running busybox coreutils, not GNU."""
        self.assertNotIn("--block-size", self.script)
        self.assertNotIn("df -h", self.script)
