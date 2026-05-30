"""Tests for formal_verification_tla runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import formal_verification_tla as ftla


class TLASpecRegistryTests(unittest.TestCase):
    def test_list_specs(self) -> None:
        specs = ftla.list_specs()
        names = [s["name"] for s in specs]
        for required in ftla.REQUIRED_SPECS:
            self.assertIn(required, names)

    def test_runtime_health_reflects_presence(self) -> None:
        health = ftla.runtime_health()
        self.assertIn("missing", health)
