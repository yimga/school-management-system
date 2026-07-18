"""Operator + tenant MFA policy, with an unweakenable floor.

Locks the layering contract: the baseline floor is always enforced, an operator's
per-tenant policy unions above the tenant's own settings, and a tenant can only
tighten (add), never weaken. The operator policy is migration-free — sourced from
a platform switch and the operator config cascade.
"""
from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.accounts.mfa_defaults import (
    OPERATOR_MFA_SETTINGS_KEY,
    effective_required_roles,
    resolve_operator_mfa,
)


def _school(**operator_mfa):
    """A minimal school-like object carrying an operator-MFA settings blob."""
    settings_blob = {OPERATOR_MFA_SETTINGS_KEY: operator_mfa} if operator_mfa else {}
    return SimpleNamespace(settings=settings_blob)


class EffectiveRequiredRolesTests(SimpleTestCase):
    def test_baseline_floor_always_present(self):
        roles = effective_required_roles(None)
        self.assertIn("ADMIN", roles)
        self.assertIn("FINANCE", roles)
        self.assertIn("BURSAR", roles)

    def test_operator_roles_union_above_empty_tenant(self):
        roles = effective_required_roles(tenant_required=[], operator_required=["HOD"])
        self.assertIn("HOD", roles)
        self.assertIn("ADMIN", roles)  # floor still there

    def test_tenant_cannot_remove_operator_or_floor(self):
        # Tenant supplies an empty list; the operator role and floor still bind.
        roles = effective_required_roles(
            tenant_required=[], operator_required=["REGISTRAR"]
        )
        self.assertIn("REGISTRAR", roles)
        self.assertIn("BURSAR", roles)

    def test_all_layers_normalized_uppercase(self):
        roles = effective_required_roles(["teacher"], operator_required=["hod"])
        self.assertIn("TEACHER", roles)
        self.assertIn("HOD", roles)


class ResolveOperatorMfaTests(SimpleTestCase):
    def test_empty_when_nothing_set(self):
        policy = resolve_operator_mfa(school=None)
        self.assertFalse(policy.require_all_staff)
        self.assertEqual(policy.required_roles, ())

    def test_empty_when_school_has_no_operator_blob(self):
        policy = resolve_operator_mfa(school=_school())
        self.assertFalse(policy.require_all_staff)
        self.assertEqual(policy.required_roles, ())

    @override_settings(MFA_OPERATOR_REQUIRE_ALL_STAFF="1")
    def test_platform_switch_forces_all_staff(self):
        policy = resolve_operator_mfa(school=None)
        self.assertTrue(policy.require_all_staff)

    def test_per_tenant_roles_and_all_staff_from_settings(self):
        policy = resolve_operator_mfa(
            school=_school(require_all_staff=True, required_roles=["HOD", "Registrar"])
        )
        self.assertTrue(policy.require_all_staff)
        self.assertEqual(policy.required_roles, ("HOD", "Registrar"))

    def test_roles_as_csv_string(self):
        policy = resolve_operator_mfa(school=_school(required_roles="HOD, Registrar"))
        self.assertEqual(set(policy.required_roles), {"HOD", "Registrar"})

    def test_fail_soft_on_broken_settings(self):
        # A non-dict settings attribute must not raise — no-op policy.
        policy = resolve_operator_mfa(school=SimpleNamespace(settings="oops"))
        self.assertFalse(policy.require_all_staff)
        self.assertEqual(policy.required_roles, ())

    def test_operator_policy_flows_into_effective_roles(self):
        # End-to-end: an operator-required role reaches the effective set even when
        # the tenant configured nothing.
        policy = resolve_operator_mfa(school=_school(required_roles=["HOD"]))
        roles = effective_required_roles([], operator_required=policy.required_roles)
        self.assertIn("HOD", roles)
