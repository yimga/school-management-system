"""A corrupt UI bundle reaches an offline box. Prove it never reaches the school.

This is the scenario the whole pipeline is built around, and it is not hypothetical: a
village link drops mid-transfer, the file lands shorter than it should, and every HTTP
status along the way was 200. Afterwards a truncated JS bundle is indistinguishable from
a good one — same path, same mtime, no error anywhere — so if it is promoted, the school
opens a broken product the next morning and nobody knows why.

The proof has four parts, and the ORDER matters:

  1. the guard detects the corruption (sha256 mismatch, not a size heuristic);
  2. the deployment STOPS — no file is promoted, so the running tree is byte-identical
     to what it was before the attempt began;
  3. the failure is RECORDED in ``EdgeDeploymentHistory``, so a support engineer can see
     the box tried, and the box remains on its previous manifest;
  4. the box still WORKS — the sync hold is released so data keeps flowing on the old
     code, which is a state the box is known to survive.

The transfer is simulated with ``source_root=`` (a local directory) rather than a mocked
socket, deliberately: the verification gate is a property of the manifest, not of HTTP,
and a test that only proves it over one transport would be testing the transport.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from django.test import TestCase, override_settings

from apps.sync_engine import upgrade_lock
from apps.sync_engine.local_upgrade import MODE_ASSETS, LocalRuntimeUpgradeManager
from apps.sync_engine.models_deployment import DeploymentState, EdgeDeploymentHistory
from apps.sync_engine.system_manifest import SystemManifestGenerator

# The running box. Deliberately a real template + a real JS bundle: these are the files
# an operator would recognise, and the ones a truncated transfer actually breaks.
_BOX_TREE = {
    "templates/dashboard/grading_card.html": "<div class='card'>v1</div>\n",
    "static/js/bundles/dashboard.js": "console.log('dashboard v1');\n",
    "static/css/tokens.css": ":root{--x:1}\n",
}

# What the operator is shipping.
_OPERATOR_TREE = {
    "templates/dashboard/grading_card.html": "<div class='card card--v2'>v2</div>\n",
    "static/js/bundles/dashboard.js": "console.log('dashboard v2');\nexport const v = 2;\n",
    "static/css/tokens.css": ":root{--x:1}\n",  # unchanged — must not be shipped
}


def _write(root: Path, files: dict) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _snapshot(root: Path) -> dict:
    return {
        str(p.relative_to(root)).replace("\\", "/"): p.read_text(encoding="utf-8")
        for p in root.rglob("*")
        if p.is_file()
    }


class CorruptUpgradeBundleTests(TestCase):
    """A bundle that does not hash to what the manifest declares must not be promoted."""

    def setUp(self):
        super().setUp()
        upgrade_lock.reset()
        self._tmp = tempfile.mkdtemp(prefix="rmc-ota-test-")
        self.box = Path(self._tmp) / "box"
        self.operator = Path(self._tmp) / "operator"
        self.staging = Path(self._tmp) / "staging"
        _write(self.box, _BOX_TREE)
        _write(self.operator, _OPERATOR_TREE)

        # Each side records what it is made of, exactly as the real deployments do.
        SystemManifestGenerator(root=self.box, version_label="2026.08.18-a").write()
        SystemManifestGenerator(root=self.operator, version_label="2026.08.22-b").write()
        self.target_manifest = _load(self.operator)
        self.box_manifest_before = _load(self.box)

    def tearDown(self):
        upgrade_lock.reset()
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().tearDown()

    def _manager(self, source: Path):
        return LocalRuntimeUpgradeManager(
            mode=MODE_ASSETS,
            target_manifest=self.target_manifest,
            source_root=source,
        )

    # ── the honest case, so the failing case means something ─────────────────
    def test_a_good_bundle_is_verified_and_applied(self):
        """Calibration: without this, a test that 'stops on corruption' proves nothing."""
        with self._settings():
            manager = self._manager(self.operator)
            manager.health_gate = lambda: (True, 1.0, "200")  # no HTTP server in a test
            result = manager.run()

        self.assertTrue(result["ok"], f"a clean bundle must apply; log={result['log']}")
        self.assertEqual(result["activation"], "swapped")
        self.assertEqual(
            (self.box / "templates/dashboard/grading_card.html").read_text(encoding="utf-8"),
            _OPERATOR_TREE["templates/dashboard/grading_card.html"],
        )
        row = EdgeDeploymentHistory.objects.order_by("-staged_at").first()
        self.assertEqual(row.state, DeploymentState.ACTIVE)

    # ── the case this module exists for ──────────────────────────────────────
    def test_corrupt_bundle_is_detected_and_the_box_is_untouched(self):
        corrupt = Path(self._tmp) / "corrupt"
        shutil.copytree(self.operator, corrupt)
        # Exactly what a dropped link produces: the file is there, shorter than declared.
        (corrupt / "static/js/bundles/dashboard.js").write_text("console.log('dash", encoding="utf-8")

        before = _snapshot(self.box)

        with self._settings():
            manager = self._manager(corrupt)
            manager.health_gate = lambda: (True, 1.0, "200")
            result = manager.run()

        # 1. detected, and named as a hash failure rather than a vague error
        self.assertFalse(result["ok"])
        self.assertIn("verify FAILED", result["error"])
        self.assertIn("static/js/bundles/dashboard.js", result["error"])

        # 2. deployment stopped BEFORE promotion — the running tree is byte-identical
        self.assertEqual(
            _snapshot(self.box),
            before,
            "a corrupt bundle changed the running tree; the verify gate ran too late",
        )
        self.assertEqual(
            (self.box / "static/js/bundles/dashboard.js").read_text(encoding="utf-8"),
            _BOX_TREE["static/js/bundles/dashboard.js"],
        )

        # 3. recorded, and the box is still on its previous manifest
        row = EdgeDeploymentHistory.objects.order_by("-staged_at").first()
        self.assertIsNotNone(row, "a failed attempt is the most useful row in the table")
        self.assertEqual(row.state, DeploymentState.FAILED)
        self.assertEqual(row.previous_manifest_hash, self.box_manifest_before["manifest_hash"])
        self.assertIn("verify FAILED", row.error)
        self.assertFalse(
            EdgeDeploymentHistory.objects.filter(state=DeploymentState.ACTIVE).exists(),
            "a bundle that failed verification must never be recorded as ACTIVE",
        )

        # 4. the box keeps working: the hold is released, so data sync resumes on old code
        self.assertFalse(
            upgrade_lock.local_is_held(),
            "a failed upgrade must not leave the rail held — that would take the school "
            "offline for data as well as for code",
        )
        failure = upgrade_lock.local_failure()
        self.assertIn("verify FAILED", failure.get("error", ""))

    def test_a_missing_file_is_refused_like_a_corrupt_one(self):
        """A transfer that stopped between files, not inside one."""
        partial = Path(self._tmp) / "partial"
        shutil.copytree(self.operator, partial)
        (partial / "templates/dashboard/grading_card.html").unlink()

        before = _snapshot(self.box)
        with self._settings():
            manager = self._manager(partial)
            manager.health_gate = lambda: (True, 1.0, "200")
            result = manager.run()

        self.assertFalse(result["ok"])
        self.assertEqual(_snapshot(self.box), before)

    def test_health_failure_after_a_clean_verify_rolls_the_tree_back(self):
        """Verification is necessary, not sufficient: valid bytes can still not boot."""
        before = _snapshot(self.box)

        with self._settings():
            manager = self._manager(self.operator)
            manager.health_gate = lambda: (False, 60.0, "connection refused")
            result = manager.run()

        self.assertFalse(result["ok"])
        self.assertIn("health gate failed", result["error"])
        self.assertEqual(
            _snapshot(self.box),
            before,
            "the rollback set did not fully restore the previous release",
        )
        row = EdgeDeploymentHistory.objects.order_by("-staged_at").first()
        self.assertEqual(row.state, DeploymentState.ROLLED_BACK)
        self.assertIsNotNone(row.reverted_at)
        self.assertFalse(upgrade_lock.local_is_held())

    def test_deployment_history_is_append_only(self):
        """A rollback target that can be deleted is not a rollback target."""
        from apps.platform_runtime.append_only import AppendOnlyDeleteError

        row = EdgeDeploymentHistory.begin(manifest_hash="a" * 64, mode=MODE_ASSETS)
        with self.assertRaises(AppendOnlyDeleteError):
            row.delete()
        with self.assertRaises(AppendOnlyDeleteError):
            EdgeDeploymentHistory.objects.all().delete()

    def test_revert_target_is_the_last_healthy_manifest_not_the_last_attempt(self):
        healthy = EdgeDeploymentHistory.begin(manifest_hash="1" * 64, mode=MODE_ASSETS)
        healthy.mark_active(health_seconds=3.0)
        newer = EdgeDeploymentHistory.begin(manifest_hash="2" * 64, mode=MODE_ASSETS)
        newer.mark_active(health_seconds=4.0)
        broken = EdgeDeploymentHistory.begin(manifest_hash="3" * 64, mode=MODE_ASSETS)
        broken.mark_failed("verify FAILED")

        self.assertEqual(EdgeDeploymentHistory.active().manifest_hash, "2" * 64)
        self.assertEqual(
            EdgeDeploymentHistory.revert_target().manifest_hash,
            "1" * 64,
            "a rollback must aim at a manifest that actually booted, never at the "
            "attempt that just failed",
        )

    # ── helper ───────────────────────────────────────────────────────────────
    def _settings(self):
        return override_settings(
            RMC_OTA_MANIFEST_PATH=str(self.box / "system_manifest.json"),
            RMC_OTA_MANIFEST_ROOT=str(self.box),
            RMC_OTA_STAGING_ROOT=str(self.staging),
            RMC_OTA_RELEASE_ROOT="",
            RMC_OTA_HOLD_TTL_SECONDS=3600,
            # The temp tree is not this project's STATIC_ROOT, and collecting the real
            # static set would take minutes and write outside the fixture. The swap
            # itself is what these tests are about.
            RMC_OTA_COLLECTSTATIC=False,
        )


def _load(root: Path) -> dict:
    import json

    return json.loads((root / "system_manifest.json").read_text(encoding="utf-8"))
