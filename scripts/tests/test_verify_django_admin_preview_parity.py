#!/usr/bin/env python3
"""Stdlib tests for verify_django_admin_preview_parity + build lock."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_django_admin_preview_parity.py"
LOCK = ROOT / "var" / "admin-approval-build-lock.json"


def _load_mod():
    spec = importlib.util.spec_from_file_location("verify_django_admin_preview_parity", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class AdminApprovalParityTests(unittest.TestCase):
    def test_lock_file_present_and_shaped(self):
        self.assertTrue(LOCK.is_file(), "var/admin-approval-build-lock.json required")
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        for key in ("build_id", "cache_bust", "sw_version", "seal", "visible_proofs"):
            self.assertIn(key, lock)
        self.assertTrue(lock["build_id"])
        self.assertTrue(lock["cache_bust"])
        self.assertTrue(str(lock["sw_version"]).startswith("sms-v"))
        self.assertIsInstance(lock["visible_proofs"], list)
        self.assertGreaterEqual(len(lock["visible_proofs"]), 3)

    def test_verifier_passes_on_clean_tree(self):
        mod = _load_mod()
        self.assertEqual(mod.main(), 0)


if __name__ == "__main__":
    unittest.main()
