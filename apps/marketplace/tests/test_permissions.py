"""Unit tests for tenant marketplace permission helpers (1000)."""

import unittest
from types import SimpleNamespace

from apps.marketplace.permissions import tenant_may_manage_marketplace


class TenantMayManageMarketplaceTests(unittest.TestCase):
    def test_anonymous_denied(self):
        u = SimpleNamespace(is_authenticated=False)
        self.assertFalse(tenant_may_manage_marketplace(u))

    def test_teacher_denied(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="TEACHER",
        )
        self.assertFalse(tenant_may_manage_marketplace(u))

    def test_admin_allowed(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="ADMIN",
        )
        self.assertTrue(tenant_may_manage_marketplace(u))

    def test_staff_allowed(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=True,
            role="TEACHER",
        )
        self.assertTrue(tenant_may_manage_marketplace(u))
