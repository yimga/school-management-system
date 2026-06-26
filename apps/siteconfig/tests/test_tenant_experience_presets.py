"""Portal experience presets + score policy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import RequestFactory, SimpleTestCase

from apps.portal.tenant_experience_command import build_tenant_experience_command
from apps.portal.tenant_role_home import role_home_show_legacy
from apps.siteconfig.tenant_experience_policy import (
    compute_weighted_experience_score,
    experience_score_band,
    tenant_experience_policy_defaults,
)
from apps.siteconfig.tenant_experience_presets import (
    PRESET_LEGACY_SHELL,
    PRESET_MINIMAL_V3,
    PRESET_PARENT_PORTAL,
    apply_experience_preset,
    detect_matching_preset,
    policy_matches_preset,
)


class TenantExperiencePresetTests(SimpleTestCase):
    def test_minimal_v3_disables_legacy_bands(self):
        policy = apply_experience_preset(PRESET_MINIMAL_V3)
        self.assertTrue(policy["use_v3_shell"])
        self.assertEqual(policy["experience_preset"], PRESET_MINIMAL_V3)
        self.assertFalse(policy["show_workspace_os_header_on_v3"])

    def test_legacy_shell_preset(self):
        policy = apply_experience_preset(PRESET_LEGACY_SHELL)
        self.assertFalse(policy["use_v3_shell"])
        self.assertEqual(policy["role_home_experience_mode"], "legacy_stack")

    def test_parent_portal_score_weights(self):
        policy = apply_experience_preset(PRESET_PARENT_PORTAL)
        self.assertEqual(policy["experience_score_profile_weight"], 60)
        self.assertEqual(policy["experience_score_country_bonus"], 10)

    def test_detect_minimal_preset(self):
        policy = apply_experience_preset(PRESET_MINIMAL_V3)
        self.assertTrue(policy_matches_preset(policy, PRESET_MINIMAL_V3))
        self.assertEqual(detect_matching_preset(policy), PRESET_MINIMAL_V3)


class TenantExperienceScorePolicyTests(SimpleTestCase):
    def test_weighted_score_favors_profile(self):
        policy = {
            **tenant_experience_policy_defaults(),
            "experience_score_profile_weight": 80,
            "experience_score_school_weight": 20,
        }
        score = compute_weighted_experience_score(100, 0, policy)
        self.assertEqual(score, 80)

    def test_country_bonus_caps_at_100(self):
        policy = {
            **tenant_experience_policy_defaults(),
            "experience_score_country_bonus": 15,
        }
        score = compute_weighted_experience_score(50, 90, policy, country_configured=True)
        self.assertEqual(score, 100)

    def test_score_bands(self):
        policy = tenant_experience_policy_defaults()
        self.assertEqual(experience_score_band(80, policy), "ready")
        self.assertEqual(experience_score_band(40, policy), "attention")
        self.assertEqual(experience_score_band(60, policy), "progress")


class TenantExperiencePersistedRoleHomeTests(SimpleTestCase):
    def test_persisted_legacy_stack_without_query(self):
        request = RequestFactory().get("/")
        request.GET = {}
        with patch(
            "apps.siteconfig.tenant_experience_policy.resolve_tenant_experience_policy",
            return_value={
                **tenant_experience_policy_defaults(),
                "use_v3_shell": True,
                "role_home_experience_mode": "legacy_stack",
            },
        ):
            self.assertTrue(role_home_show_legacy(request))

    def test_simple_zero_overrides_persisted_legacy(self):
        request = RequestFactory().get("/?simple=0")
        with patch(
            "apps.siteconfig.tenant_experience_policy.resolve_tenant_experience_policy",
            return_value={
                **tenant_experience_policy_defaults(),
                "role_home_experience_mode": "legacy_stack",
            },
        ):
            self.assertFalse(role_home_show_legacy(request))


class TenantExperienceCommandScoreTests(SimpleTestCase):
    def test_command_exposes_score_band(self):
        request = MagicMock()
        request.school = None
        request.site_settings = None
        request.SITE = None
        request.user = MagicMock(email="a@b.com", first_name="A")
        request.user.get_full_name.return_value = "Ada Lovelace"
        with patch(
            "apps.portal.tenant_experience_command._safe_reverse",
            return_value="/profile/",
        ):
            with patch(
                "apps.siteconfig.tenant_experience_policy.resolve_tenant_experience_policy",
                return_value=tenant_experience_policy_defaults(),
            ):
                payload = build_tenant_experience_command(request, "PARENT")
        self.assertIn(payload["score_band"], {"ready", "progress", "attention"})
        self.assertIn("score_ready_threshold", payload)
