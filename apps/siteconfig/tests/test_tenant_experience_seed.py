"""Provision-time tenant experience policy seed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.siteconfig.tenant_experience_presets import PRESET_MINIMAL_V3, PRESET_PARENT_PORTAL
from apps.siteconfig.tenant_experience_seed import (
    build_provision_tenant_experience_policy,
    ensure_tenant_experience_policy,
)


class TenantExperienceSeedTests(SimpleTestCase):
    def test_build_provision_policy_defaults(self):
        policy = build_provision_tenant_experience_policy()
        self.assertEqual(policy["experience_preset"], PRESET_MINIMAL_V3)
        self.assertEqual(policy["role_experience_presets"]["PARENT"], PRESET_PARENT_PORTAL)
        self.assertTrue(policy["_provision_seeded"])

    def test_ensure_skips_when_operator_configured(self):
        school = MagicMock(slug="demo-school", country_code="CM")
        with patch(
            "apps.siteconfig.tenant_experience_seed._existing_policy",
            return_value={"use_v3_shell": False, "show_mission_strip": True},
        ):
            result = ensure_tenant_experience_policy(school, apply=False)
        self.assertEqual(result["use_v3_shell"], False)

    def test_ensure_applies_when_empty(self):
        school = MagicMock(slug="new-school", country_code="AE", pk=1)
        with patch("apps.siteconfig.tenant_experience_seed._existing_policy", return_value=None):
            with patch("apps.siteconfig.models.SiteSettings") as site_cls:
                site = MagicMock()
                site.cockpit_payload = {}
                site_cls.objects.first.return_value = site
                result = ensure_tenant_experience_policy(school, apply=True)
        self.assertTrue(site_cls.set_cockpit_payload.called)
        self.assertEqual(result["experience_preset"], PRESET_MINIMAL_V3)
