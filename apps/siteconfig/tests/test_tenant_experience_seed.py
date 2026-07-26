"""Provision-time tenant experience policy seed."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.siteconfig.tenant_experience_presets import PRESET_MINIMAL_V3
from apps.siteconfig.tenant_experience_seed import (
    build_provision_tenant_experience_policy,
    ensure_tenant_experience_policy,
)


class TenantExperienceSeedTests(SimpleTestCase):
    def test_build_provision_policy_defaults(self):
        policy = build_provision_tenant_experience_policy()
        self.assertEqual(policy["experience_preset"], PRESET_MINIMAL_V3)
        self.assertTrue(policy["use_v3_shell"])
        # Minimal-v3 seeds NO per-role overrides — the default is an empty map so
        # every role inherits the school-level preset (role overrides are an
        # operator opt-in, not a provision default).
        self.assertEqual(policy["role_experience_presets"], {})
        self.assertTrue(policy["_provision_seeded"])

    def test_ensure_skips_when_operator_configured(self):
        # ensure_tenant_experience_policy now reads site.cockpit_payload inline; a
        # non-empty operator-configured policy (no _provision_seeded marker) is
        # returned unchanged when force is False and is never re-persisted.
        existing = {"use_v3_shell": False, "show_mission_strip": True}
        site = SimpleNamespace(
            cockpit_payload={"tenant_experience_policy": existing}
        )
        with patch(
            "apps.siteconfig.tenant_experience_seed.persist_tenant_experience_policy"
        ) as mock_persist:
            result = ensure_tenant_experience_policy(site)
        self.assertEqual(result["use_v3_shell"], False)
        mock_persist.assert_not_called()

    def test_ensure_applies_when_empty(self):
        # An empty cockpit_payload seeds the default provision policy and persists
        # it through persist_tenant_experience_policy(site, policy).
        site = SimpleNamespace(cockpit_payload={})
        with patch(
            "apps.siteconfig.tenant_experience_seed.persist_tenant_experience_policy"
        ) as mock_persist:
            result = ensure_tenant_experience_policy(site)
        mock_persist.assert_called_once()
        self.assertEqual(result["experience_preset"], PRESET_MINIMAL_V3)
        self.assertTrue(result["_provision_seeded"])
