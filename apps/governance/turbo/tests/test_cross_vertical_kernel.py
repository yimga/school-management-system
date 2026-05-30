"""Tests for cross_vertical_kernel runtime."""

from __future__ import annotations

import unittest

from apps.governance.turbo import cross_vertical_kernel as cvk


class CrossVerticalKernelTests(unittest.TestCase):
    def test_alternate_vertical_smoke_pack(self) -> None:
        result = cvk.run_alternate_vertical_smoke_pack()
        self.assertEqual(result["isolated_count"], 1)
        self.assertEqual(result["stats"]["tenants"], 2)

    def test_disallowed_vertical_raises(self) -> None:
        kernel = cvk.GovernanceKernel()
        with self.assertRaises(cvk.CrossVerticalKernelError):
            kernel.register_tenant(cvk.KernelTenant("x", "not_a_vertical", "X"))

    def test_vertical_mismatch_link_raises(self) -> None:
        kernel = cvk.GovernanceKernel()
        kernel.register_tenant(cvk.KernelTenant("t1", "health", "T1"))
        kernel.register_org(cvk.KernelOrg("o1", "education", "O1"))
        with self.assertRaises(cvk.CrossVerticalKernelError):
            kernel.link("t1", "o1")
