"""Tests for the baseline MFA-required-roles enforcement."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.accounts.mfa_defaults import (
    BASELINE_REQUIRED_ROLES,
    effective_required_roles,
    role_requires_mfa,
)


class BaselineRolesTests(SimpleTestCase):
    def test_baseline_includes_high_risk_roles(self):
        for role in (
            "PLATFORM_ADMIN",
            "SUPER_ADMIN",
            "FINANCE_ADMIN",
            "FINANCE",
            "BURSAR",
            "SCHOOL_ADMIN",
            "AUDITOR",
        ):
            self.assertIn(role, BASELINE_REQUIRED_ROLES, f"baseline missing {role}")

    def test_effective_set_contains_baseline_when_tenant_passes_none(self):
        eff = effective_required_roles(None)
        for role in BASELINE_REQUIRED_ROLES:
            self.assertIn(role.upper(), eff)

    def test_tenant_can_extend_but_not_remove_baseline(self):
        eff = effective_required_roles(["TEACHER"])
        self.assertIn("TEACHER", eff)
        for role in BASELINE_REQUIRED_ROLES:
            self.assertIn(role.upper(), eff)

    @override_settings(MFA_REQUIRED_ROLES_EXTRA=["custom_role"])
    def test_settings_extra_roles_added(self):
        eff = effective_required_roles(None)
        self.assertIn("CUSTOM_ROLE", eff)


class RoleRequiresMFATests(SimpleTestCase):
    def test_high_risk_role_requires_mfa_even_without_tenant_config(self):
        self.assertTrue(role_requires_mfa("FINANCE_ADMIN", None))
        self.assertTrue(role_requires_mfa("super_admin", None))  # case-insensitive

    def test_low_risk_role_does_not_require_by_default(self):
        self.assertFalse(role_requires_mfa("STUDENT", None))
        self.assertFalse(role_requires_mfa("PARENT", []))

    def test_tenant_can_extend_to_low_risk_role(self):
        self.assertTrue(role_requires_mfa("TEACHER", ["TEACHER"]))

    def test_empty_role_does_not_match(self):
        self.assertFalse(role_requires_mfa(None, None))
        self.assertFalse(role_requires_mfa("", ["FINANCE_ADMIN"]))
