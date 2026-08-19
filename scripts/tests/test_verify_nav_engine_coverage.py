"""Stdlib tests for verify_nav_engine_coverage static checks."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import verify_nav_engine_coverage as m  # noqa: E402


class NavEngineCoverageStaticTests(unittest.TestCase):
    def test_live_tree_static_checks_clean(self):
        self.assertEqual(m._static_checks(), [])
