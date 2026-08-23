"""A full-lane upgrade must actually swap, not honestly refuse forever.

The ordinary image is one tree (`COPY . .` into /app), and overwriting `.py` files under a
live interpreter cannot be made atomic — so `local_upgrade` correctly reports
`deferred: apply with an image rebuild`. That is honest, and it also means the full lane
never ran on a real box: every code upgrade waited for someone to rebuild an image and
push it to a school.

The release layout is the shape that makes it real — `releases/<hash>` beside the current
tree, `current` repointed in one rename. These tests pin the two halves that make it safe:
the deployment WIRING must exist (a symlink nothing serves from is decoration), and the
reload must be configured (a swapped file under a running interpreter changes nothing).
"""
from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from apps.sync_engine import local_upgrade, upgrade_runtime

REPO = Path(__file__).resolve().parents[3]


def _read(rel):
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


class DeploymentWiringTests(SimpleTestCase):
    """A release root the web server does not serve from is decoration."""

    def test_the_entrypoint_serves_from_the_release_symlink_when_one_is_configured(self):
        entrypoint = _read("deploy/selfhost/entrypoint.web.sh")
        self.assertIn("RMC_OTA_RELEASE_ROOT", entrypoint)
        self.assertIn("rmc_release_layout_prepare", entrypoint)
        self.assertIn(
            'cd "${RMC_SERVE_DIR}"',
            entrypoint,
            "gunicorn does not run from the release symlink, so flipping it changes "
            "nothing about what the box serves",
        )

    def test_the_release_layout_helper_exists_and_is_sourced(self):
        self.assertTrue((REPO / "deploy/selfhost/release_layout.sh").is_file())
        self.assertIn("release_layout.sh", _read("deploy/selfhost/entrypoint.web.sh"))

    def test_the_layout_is_opt_in_so_an_unset_box_boots_exactly_as_before(self):
        """An appliance that fails to boot is far worse than one that defers an upgrade."""
        entrypoint = _read("deploy/selfhost/entrypoint.web.sh")
        # The unconditional gunicorn exec must still be present as the fall-through.
        self.assertRegex(
            entrypoint,
            r'echo "\[selfhost\] starting gunicorn"\s*\n\s*export GUNICORN_PIDFILE',
            "the plain boot path was removed; a box without a release root would not start",
        )

    def test_the_seed_is_idempotent_by_construction(self):
        """Re-seeding every boot would copy the whole tree AND destroy the rollback target."""
        helper = _read("deploy/selfhost/release_layout.sh")
        self.assertIn('if [[ -L "${current}" && -d "${current}" ]]; then', helper)

    def test_the_symlink_is_repointed_atomically(self):
        """A flip that is briefly absent is a window where the box serves nothing."""
        helper = _read("deploy/selfhost/release_layout.sh")
        self.assertIn("mv -Tf", helper)


class ReloadIsConfiguredTests(SimpleTestCase):
    """A swapped file under a running interpreter changes nothing until it reloads."""

    def test_gunicorn_writes_a_pidfile_when_asked(self):
        conf = _read("config/gunicorn.conf.py")
        self.assertIn("GUNICORN_PIDFILE", conf)
        self.assertIn("pidfile = _pidfile", conf)

    def test_the_entrypoint_exports_a_pidfile_on_both_boot_paths(self):
        entrypoint = _read("deploy/selfhost/entrypoint.web.sh")
        self.assertEqual(
            len(re.findall(r"export GUNICORN_PIDFILE", entrypoint)),
            2,
            "only one boot path exports a pidfile, so the other silently degrades to "
            "'reload NOT configured' and every upgrade waits for a container restart",
        )

    @override_settings(RMC_OTA_WORKER_RELOAD_PIDFILE="", RMC_OTA_WORKER_RELOAD_COMMAND="")
    def test_an_unconfigured_box_still_reports_rather_than_guessing(self):
        outcome = upgrade_runtime.reload_workers()
        self.assertIn("NOT configured", outcome)

    def test_the_setting_falls_back_to_the_gunicorn_pidfile(self):
        """Two env vars that must name the same file is a configuration trap."""
        settings_src = _read("config/settings.py")
        self.assertIn('os.getenv("GUNICORN_PIDFILE", "")', settings_src)


class DeferralContractTests(SimpleTestCase):
    """Without a release root the manager must still refuse, and say why."""

    @override_settings(RMC_OTA_RELEASE_ROOT="")
    def test_no_release_root_means_no_release_root(self):
        self.assertIsNone(local_upgrade.release_root())

    @override_settings(RMC_OTA_RELEASE_ROOT="/srv/rmc")
    def test_a_configured_release_root_is_resolved(self):
        root = local_upgrade.release_root()
        self.assertIsNotNone(
            root,
            "RMC_OTA_RELEASE_ROOT was set and the manager still saw nothing, so the full "
            "lane would defer forever on a box that is laid out for it",
        )

    def test_the_deferral_message_still_tells_an_operator_what_to_do(self):
        source = _read("apps/sync_engine/local_upgrade.py")
        self.assertIn("RMC_OTA_RELEASE_ROOT unset", source)
        self.assertIn("apply with an image rebuild", source)
