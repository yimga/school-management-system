"""Unit tests for tenant marketplace permission helpers (1000)."""

import unittest
from types import SimpleNamespace
from unittest import mock

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

    def test_proprietor_allowed(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="PROPRIETOR",
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

    def test_school_owner_allowed_when_school_scoped(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="TEACHER",
        )
        school = SimpleNamespace(pk=1)
        with mock.patch(
            "apps.accounts.views_owner_console.is_school_owner",
            return_value=True,
        ):
            self.assertTrue(tenant_may_manage_marketplace(u, school=school))

    def test_non_owner_teacher_denied_when_school_scoped(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="TEACHER",
        )
        school = SimpleNamespace(pk=1)
        with mock.patch(
            "apps.accounts.views_owner_console.is_school_owner",
            return_value=False,
        ):
            self.assertFalse(tenant_may_manage_marketplace(u, school=school))
