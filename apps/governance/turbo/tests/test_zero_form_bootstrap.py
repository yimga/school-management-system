"""Tests for zero_form_bootstrap runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import zero_form_bootstrap as zfb


class ZeroFormBootstrapTests(unittest.TestCase):
    def test_bootstrap_for_known_iso(self) -> None:
        result = zfb.bootstrap_from_iso("GB")
        self.assertEqual(result["bootstrap_status"], "ready_for_confirm")
        self.assertEqual(result["country_iso"], "GB")
        self.assertIn("official_languages", result)

    def test_bootstrap_for_unknown_iso(self) -> None:
        result = zfb.bootstrap_from_iso("ZZ")
        self.assertEqual(result["bootstrap_status"], "no_matrix_shard")
