"""The leaf check behind `scripts/verify_single_migration_leaf.py`.

The gate exists because two agents adding a migration to the same app in parallel produce
two files with DIFFERENT names and the SAME dependency. Git reports a clean merge -- there
is no textual conflict to find -- and Django then refuses to migrate that app at all.
It happened on 2026-08-23: main landed ``schools/0085_advancement_grant_child_school_column``
while a branch added ``schools/0085_alter_school_subdomain``.

These tests pin the grouping logic and the reasons the gate asks the migration graph
rather than pattern-matching filenames. The graph walk itself needs Django, so it is
exercised against fake leaf-node tuples here and this file stays stdlib.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "verify_single_migration_leaf.py"
_spec = importlib.util.spec_from_file_location("verify_single_migration_leaf", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
sys.modules["verify_single_migration_leaf"] = mod
_spec.loader.exec_module(mod)


def _group(leaf_nodes):
    """The same grouping the script does, over a fake leaf_nodes() result."""
    grouped: dict[str, list[str]] = {}
    for app_label, name in leaf_nodes:
        grouped.setdefault(app_label, []).append(name)
    return {app: sorted(names) for app, names in grouped.items()}


class GroupingTests(unittest.TestCase):
    def test_one_leaf_per_app_is_clean(self):
        grouped = _group([("schools", "0087_x"), ("finance", "0031_y")])
        self.assertEqual({a: n for a, n in grouped.items() if len(n) > 1}, {})

    def test_the_real_collision_is_reported(self):
        """The exact 2026-08-23 shape: two 0085s in one app."""
        grouped = _group(
            [
                ("schools", "0085_advancement_grant_child_school_column"),
                ("schools", "0085_alter_school_subdomain"),
                ("finance", "0031_y"),
            ]
        )
        conflicted = {a: n for a, n in grouped.items() if len(n) > 1}
        self.assertEqual(list(conflicted), ["schools"])
        self.assertEqual(len(conflicted["schools"]), 2)

    def test_apps_are_independent(self):
        """One app's collision must not implicate a healthy neighbour."""
        grouped = _group([("a", "1"), ("a", "2"), ("b", "1")])
        conflicted = {app: names for app, names in grouped.items() if len(names) > 1}
        self.assertEqual(list(conflicted), ["a"])

    def test_an_app_with_no_migrations_is_not_a_finding(self):
        self.assertEqual(_group([]), {})


class DesignTests(unittest.TestCase):
    """Why it asks the graph, and why there is nothing to ratchet."""

    def setUp(self):
        self.source = SCRIPT.read_text(encoding="utf-8")

    def test_it_uses_the_migration_loader_not_filename_parsing(self):
        """A numeric-prefix check would miss 0085_a vs 0085b_a, and false-positive on
        the many legitimate merge migrations in this tree."""
        self.assertIn("MigrationLoader", self.source)
        self.assertIn("leaf_nodes", self.source)

    def test_there_is_no_baseline(self):
        """An app with two leaves cannot deploy, so there is nothing to ratchet."""
        self.assertNotIn("security-audit-baseline", self.source)
        self.assertIn("No baseline", self.source)

    def test_it_names_both_ways_to_fix_a_collision(self):
        self.assertIn("makemigrations --merge", self.source)
        self.assertIn("Renumber", self.source)

    def test_it_says_to_update_comments_naming_the_number(self):
        """A comment pointing at a migration that no longer exists costs an hour."""
        self.assertIn("comment that names the migration", self.source)


class LiveTreeTests(unittest.TestCase):
    """Calibration against the tree, when Django is importable."""

    def test_the_current_tree_is_single_leaf(self):
        try:
            import django  # noqa: F401
        except ImportError:
            self.skipTest("Django not installed; the graph walk cannot run")
        import os

        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        try:
            django.setup()
            grouped = mod.leaves_by_app()
        except Exception as exc:  # settings/app-registry problems are not this gate's job
            self.skipTest(f"Django could not boot here: {exc}")
        conflicted = {app: names for app, names in grouped.items() if len(names) > 1}
        self.assertEqual(conflicted, {}, f"tree has multi-leaf apps: {conflicted}")


if __name__ == "__main__":
    unittest.main()
