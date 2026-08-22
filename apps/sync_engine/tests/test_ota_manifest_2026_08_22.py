"""The manifest must be a FACT about a tree, not a description of when it was built.

Everything downstream — the handshake, the delta, the verify gate, the parity claim —
rests on one property: two identical trees hash identically, and any difference in
content changes the hash. If that is not true then "we are in parity" is a guess, and a
box can be told it is current when it is not, or upgraded forever in a loop.

These are pure-function tests over temp directories. No database, no network.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.sync_engine import upgrade_delta
from apps.sync_engine.system_manifest import (
    APP_CORE,
    DATA_ASSET,
    MIGRATION,
    STATIC_ASSET,
    UI_TEMPLATE,
    SystemManifestGenerator,
    verify_tree,
)


def _tree(root: Path, files: dict) -> None:
    for relative, content in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


_SAMPLE = {
    "apps/finance/models.py": "class Invoice: pass\n",
    "apps/finance/migrations/0094_ledger_split.py": "# migration\n",
    "templates/dashboard/grading_card.html": "<div>card</div>\n",
    "static/js/bundles/dashboard.js": "console.log(1)\n",
    "config/settings.py": "DEBUG = False\n",
}


class ManifestDeterminismTests(SimpleTestCase):
    def test_identical_trees_hash_identically(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _tree(Path(a), _SAMPLE)
            _tree(Path(b), _SAMPLE)
            self.assertEqual(
                SystemManifestGenerator(root=Path(a)).digest(),
                SystemManifestGenerator(root=Path(b)).digest(),
                "two identical trees produced different manifest hashes — every parity "
                "claim built on this hash would be meaningless",
            )

    def test_hash_ignores_generation_time_and_root(self):
        """A rebuild of unchanged source must not look like an upgrade."""
        with tempfile.TemporaryDirectory() as a:
            _tree(Path(a), _SAMPLE)
            first = SystemManifestGenerator(root=Path(a)).build()
            second = SystemManifestGenerator(root=Path(a)).build()
            self.assertEqual(first["manifest_hash"], second["manifest_hash"])
            # ...and the field that DOES vary is present, so the hash is not accidentally
            # stable merely because nothing time-varying was recorded at all.
            self.assertTrue(first["generated_at"])

    def test_one_changed_byte_changes_the_hash(self):
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            before = SystemManifestGenerator(root=root).digest()
            (root / "templates/dashboard/grading_card.html").write_text("<div>card2</div>\n", encoding="utf-8")
            self.assertNotEqual(before, SystemManifestGenerator(root=root).digest())

    def test_databases_caches_and_collected_static_are_excluded(self):
        """A manifest is the shippable surface, never a backup of the checkout."""
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            _tree(root, {
                "db_playwright.sqlite3": "x",
                "staticfiles/js/bundles/dashboard.abc123.js": "collected",
                "apps/finance/__pycache__/models.cpython-312.pyc": "x",
                "media/photos/student.jpg": "x",
                ".rmc_ota_staging/deadbeef/apps/finance/models.py": "staged",
            })
            paths = set(SystemManifestGenerator(root=root).entries())
            for excluded in (
                "db_playwright.sqlite3",
                "staticfiles/js/bundles/dashboard.abc123.js",
                "apps/finance/__pycache__/models.cpython-312.pyc",
                "media/photos/student.jpg",
                ".rmc_ota_staging/deadbeef/apps/finance/models.py",
            ):
                self.assertNotIn(excluded, paths, f"{excluded} must never be shipped in a manifest")


class CategorisationTests(SimpleTestCase):
    def test_categories_are_assigned_by_shape(self):
        cases = {
            "apps/finance/migrations/0094_ledger_split.py": MIGRATION,
            "templates/dashboard/grading_card.html": UI_TEMPLATE,
            "static/js/bundles/dashboard.js": STATIC_ASSET,
            "apps/finance/models.py": APP_CORE,
            # Non-python data. Read at runtime, never imported, so it can never need a
            # reload -- see test_a_gate_run_on_the_operator_is_not_a_code_change.
            "docs/generated/security_surface_audit.json": DATA_ASSET,
            "var/admin-surface-platformwide-sweep.json": DATA_ASSET,
            "docs/generated/country_governance_matrix/ng.json": DATA_ASSET,
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                self.assertEqual(SystemManifestGenerator.categorise(path), expected)

    def test_a_gate_run_on_the_operator_is_not_a_code_change(self):
        """The fleet must not take the full lane to receive a regenerated audit report.

        1713 files -- 13.35% of the manifest -- are audit output under docs/generated/
        and var/, and every pre_push_boundary_check.py run on the operator rewrites some
        of them. While they were classified APP_CORE, that made a GATE RUN indistinguishable
        from a code change: every box in the fleet would freeze writes, pause workers, run
        a migration precheck, swap its tree and sit out a health gate, to receive a json
        recording a test duration.
        """
        base = {
            "manifest_hash": "a" * 64,
            "files": {"docs/generated/security_surface_audit.json": {"sha256": "1" * 64, "bytes": 10, "category": DATA_ASSET}},
        }
        target = {
            "manifest_hash": "b" * 64,
            "files": {"docs/generated/security_surface_audit.json": {"sha256": "2" * 64, "bytes": 11, "category": DATA_ASSET}},
        }
        delta = upgrade_delta.compute_delta(base, target)

        self.assertEqual(delta["file_count"], 1)
        self.assertFalse(
            upgrade_delta.requires_code_reload(delta),
            "a regenerated audit artifact was treated as a code change; every box in the "
            "fleet would take the full upgrade lane for it",
        )
        self.assertFalse(upgrade_delta.requires_migration(delta))

    def test_python_is_still_a_code_change(self):
        """Calibration: without this, the test above passes by disabling the full lane."""
        base = {
            "manifest_hash": "a" * 64,
            "files": {"apps/finance/models.py": {"sha256": "1" * 64, "bytes": 10, "category": APP_CORE}},
        }
        target = {
            "manifest_hash": "b" * 64,
            "files": {"apps/finance/models.py": {"sha256": "2" * 64, "bytes": 11, "category": APP_CORE}},
        }
        self.assertTrue(upgrade_delta.requires_code_reload(upgrade_delta.compute_delta(base, target)))

    def test_data_assets_ship_rather_than_being_excluded(self):
        """They are product surface: an operator dashboard renders them.

        super_views_enterprise_security loads nine of these json files and
        views_cockpit_previews serves the generated preview HTML. Dropping them from the
        manifest to stop the churn would leave a box with empty dashboards, which is why
        the fix is the CATEGORY and not an exclusion.
        """
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, {
                "docs/generated/security_surface_audit.json": "{}",
                "var/admin-surface-platformwide-sweep.json": "{}",
            })
            paths = set(SystemManifestGenerator(root=root).entries())

        self.assertIn("docs/generated/security_surface_audit.json", paths)
        self.assertIn("var/admin-surface-platformwide-sweep.json", paths)

    def test_migration_index_and_app_label_are_extracted(self):
        path = "apps/finance/migrations/0094_ledger_split.py"
        self.assertEqual(SystemManifestGenerator.app_label_for(path), "finance")
        self.assertEqual(SystemManifestGenerator.migration_index_for(path), "0094")

    def test_migration_heads_come_from_files_not_the_database(self):
        """A manifest must be buildable in a Docker layer with no database in existence."""
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, {
                "apps/finance/migrations/0093_x.py": "#",
                "apps/finance/migrations/0094_y.py": "#",
                "apps/people/migrations/0087_z.py": "#",
            })
            self.assertEqual(
                SystemManifestGenerator(root=root).migration_heads(),
                {"finance": "0094", "people": "0087"},
            )


class DeltaTests(SimpleTestCase):
    def _manifests(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _tree(Path(a), _SAMPLE)
            base = SystemManifestGenerator(root=Path(a)).build()
            after = dict(_SAMPLE)
            after["templates/dashboard/grading_card.html"] = "<div>v2</div>\n"
            after["apps/finance/migrations/0095_receipt_series.py"] = "# new\n"
            del after["config/settings.py"]
            _tree(Path(b), after)
            target = SystemManifestGenerator(root=Path(b)).build()
            return base, target

    def test_delta_names_exactly_what_changed(self):
        base, target = self._manifests()
        delta = upgrade_delta.compute_delta(base, target)
        self.assertEqual([r["path"] for r in delta["added"]], ["apps/finance/migrations/0095_receipt_series.py"])
        self.assertEqual([r["path"] for r in delta["changed"]], ["templates/dashboard/grading_card.html"])
        self.assertEqual(delta["removed"], ["config/settings.py"])
        self.assertTrue(delta["complete"])

    def test_unchanged_files_are_never_shipped(self):
        base, target = self._manifests()
        delta = upgrade_delta.compute_delta(base, target)
        shipped = {r["path"] for r in delta["added"] + delta["changed"]}
        self.assertNotIn("static/js/bundles/dashboard.js", shipped)
        self.assertNotIn("apps/finance/models.py", shipped)

    def test_asset_only_delta_excludes_code_and_is_marked_incomplete(self):
        """Half an upgrade is legitimate — but it must never claim to reach the target."""
        base, target = self._manifests()
        delta = upgrade_delta.asset_only_delta(base, target)
        self.assertEqual([r["path"] for r in delta["changed"]], ["templates/dashboard/grading_card.html"])
        self.assertEqual(delta["migrations"], [])
        self.assertFalse(
            delta["complete"],
            "an asset-only delta must report complete=False, or a box would stamp the "
            "target manifest hash after fetching part of it",
        )
        self.assertFalse(upgrade_delta.requires_code_reload(delta))

    def test_full_delta_reports_migrations_and_code_reload(self):
        base, target = self._manifests()
        delta = upgrade_delta.compute_delta(base, target)
        self.assertTrue(upgrade_delta.requires_migration(delta))
        self.assertTrue(upgrade_delta.requires_code_reload(delta))

    def test_truncation_is_reported_not_hidden(self):
        base, target = self._manifests()
        delta = upgrade_delta.compute_delta(base, target, max_files=1)
        self.assertTrue(delta["truncated"])
        self.assertFalse(delta["complete"])
        self.assertGreaterEqual(delta["omitted_count"], 1)
        self.assertIn("TRUNCATED", upgrade_delta.describe(delta))

    def test_empty_base_yields_the_whole_target(self):
        """A box with no manifest must be able to converge, not be told it is current."""
        _base, target = self._manifests()
        delta = upgrade_delta.compute_delta({}, target)
        self.assertEqual(delta["file_count"], len(target["files"]))


class VerifyTreeTests(SimpleTestCase):
    def test_verify_passes_on_a_faithful_copy(self):
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            manifest = SystemManifestGenerator(root=root).build()
            report = verify_tree(manifest, root)
            self.assertTrue(report["ok"])
            self.assertEqual(report["checked"], len(_SAMPLE))

    def test_verify_catches_a_truncated_file(self):
        """The exact failure a dropped link produces: shorter bytes, every HTTP 200."""
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            manifest = SystemManifestGenerator(root=root).build()
            target = root / "static/js/bundles/dashboard.js"
            target.write_text("console.log(", encoding="utf-8")  # truncated mid-statement
            report = verify_tree(manifest, root)
            self.assertFalse(report["ok"])
            self.assertIn("static/js/bundles/dashboard.js", report["mismatched"])

    def test_verify_catches_a_missing_file(self):
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            manifest = SystemManifestGenerator(root=root).build()
            os.remove(root / "templates/dashboard/grading_card.html")
            report = verify_tree(manifest, root)
            self.assertFalse(report["ok"])
            self.assertIn("templates/dashboard/grading_card.html", report["missing"])


class ManifestFileRoundTripTests(SimpleTestCase):
    def test_written_manifest_reports_its_own_hash(self):
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            generator = SystemManifestGenerator(root=root, version_label="2026.08.22-b")
            written = generator.write()
            payload = json.loads(written.read_text(encoding="utf-8"))
            self.assertEqual(payload["manifest_hash"], generator.digest())
            self.assertEqual(payload["version_label"], "2026.08.22-b")
            self.assertEqual(payload["file_count"], len(_SAMPLE))

    def test_a_manifest_never_describes_itself(self):
        """Otherwise writing it changes the hash it just recorded, forever."""
        with tempfile.TemporaryDirectory() as a:
            root = Path(a)
            _tree(root, _SAMPLE)
            generator = SystemManifestGenerator(root=root)
            before = generator.digest()
            generator.write()
            self.assertEqual(SystemManifestGenerator(root=root).digest(), before)
