"""Tests for adversarial_redteam runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import adversarial_redteam as art


class AdversarialRedteamTests(unittest.TestCase):
    def test_all_probes_pass_under_clean_state(self) -> None:
        result = art.run_all_probes()
        self.assertEqual(result["failed_count"], 0, msg=result)

    def test_probe_count_matches_registry(self) -> None:
        result = art.run_all_probes()
        self.assertEqual(result["probe_count"], len(art.PROBES))
