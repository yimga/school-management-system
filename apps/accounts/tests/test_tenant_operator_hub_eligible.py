"""Tenant operator hub visibility (Phase 3–4 shell parity)."""

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.accounts.permissions import tenant_operator_hub_eligible


class TenantOperatorHubEligibleTests(SimpleTestCase):
    def test_anonymous_false(self):
        u = SimpleNamespace(is_authenticated=False)
        self.assertFalse(tenant_operator_hub_eligible(u))

    def test_superuser_true(self):
        u = SimpleNamespace(is_authenticated=True, is_superuser=True, is_staff=False)
        self.assertTrue(tenant_operator_hub_eligible(u))

    def test_teacher_false_even_if_staff(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=True,
            role="TEACHER",
        )
        u.has_feature_permission = lambda _c: False
        self.assertFalse(tenant_operator_hub_eligible(u))

    def test_staff_non_excluded_true(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=True,
            role="PRINCIPAL",
        )
        u.has_feature_permission = lambda _c: False
        self.assertTrue(tenant_operator_hub_eligible(u))

    def test_settings_manage_true(self):
        u = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            is_staff=False,
            role="TEACHER",
        )
        u.has_feature_permission = lambda c: c == "settings.manage"
        self.assertTrue(tenant_operator_hub_eligible(u))
