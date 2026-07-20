"""Lock the offline-capability implementation gate.

Stdlib-only (mirrors the gate, which runs in the dependency-free CI job). Loads
the script by path so it works without a package install.
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "verify_offline_capability_implementation.py"
)
_spec = importlib.util.spec_from_file_location("_offline_cap_gate", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(mod)


class AssignedValueTests(unittest.TestCase):
    def test_handles_plain_and_annotated_assign(self):
        tree = ast.parse("X: dict = {'a': 1}\nY = {'b': 2}\n")
        x = y = None
        for node in ast.walk(tree):
            x = x or mod._assigned_value(node, "X")
            y = y or mod._assigned_value(node, "Y")
        self.assertIsInstance(x, ast.Dict)
        self.assertIsInstance(y, ast.Dict)

    def test_iter_set_literals_unwraps_frozenset(self):
        tree = ast.parse("V = frozenset({'a', 'b'})")
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign))
        self.assertEqual(
            {e.value for e in mod._iter_set_literals(node.value)}, {"a", "b"}
        )


class RealTreeTests(unittest.TestCase):
    def test_declared_capabilities_match_taxonomy(self):
        self.assertEqual(
            mod._declared_queued_write_capabilities(),
            {
                "enable_offline_form_queue",
                "enable_offline_attendance_sync",
                "enable_offline_grade_sync",
                "enable_offline_homework_sync",
                "enable_offline_fee_payment_sync",
                "enable_offline_migration_cloud_upload",
            },
        )

    def test_wal_registry_and_allowlist_agree(self):
        registry = mod._wal_string_set(mod.WAL_WRITERS, "_REGISTRY")
        allowed = mod._wal_string_set(mod.WAL_CONSUMERS, "_ALLOWED_DOMAINS")
        self.assertIn("attendance", registry)
        self.assertIn("grade", registry)
        # Producer (registry) and consumer allow-list must list the same domains,
        # else a write is accepted-but-undrained or drained-but-rejected.
        self.assertEqual(registry, allowed)

    def test_real_tree_is_honest(self):
        # Every declared capability has a real producer + applier today.
        self.assertEqual(mod.main([]), 0)


class TheaterDetectionTests(unittest.TestCase):
    def test_declared_capability_without_implementation_fails(self):
        ghost = "enable_offline_ghost_sync"
        ghost_spec = dict(mod._CAPABILITY_SPEC)
        ghost_spec[ghost] = {
            "sodp_tokens": ("ghost.nope",),
            "sodp_members": ("GHOST_NOPE",),
            "wal_domains": (),
            "form_kinds": (),
            "generic": False,
        }
        with mock.patch.object(
            mod,
            "_declared_queued_write_capabilities",
            return_value=set(ghost_spec),
        ), mock.patch.object(mod, "_CAPABILITY_SPEC", ghost_spec):
            self.assertEqual(mod.main([]), 1)

    def test_unmapped_taxonomy_capability_fails(self):
        with mock.patch.object(
            mod,
            "_declared_queued_write_capabilities",
            return_value=set(mod._CAPABILITY_SPEC) | {"enable_offline_unmapped_sync"},
        ):
            self.assertEqual(mod.main([]), 1)


if __name__ == "__main__":
    unittest.main()
