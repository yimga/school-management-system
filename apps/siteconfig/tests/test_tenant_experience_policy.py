"""Tenant experience policy resolver + cockpit configure round-trip."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase

from apps.portal.tenant_role_home import is_tp_v3_tenant_shell_request
from apps.siteconfig.forms_cockpit import CockpitPayloadForm
from apps.siteconfig.tenant_experience_policy import (
    derive_chrome_flags,
    filter_setup_wizard_stages,
    resolve_tenant_experience_policy,
    tenant_experience_policy_defaults,
    user_may_configure_tenant_experience,
)


class TenantExperiencePolicyDefaultsTests(SimpleTestCase):
    def test_defaults_preserve_v3_shell_on(self):
        defaults = tenant_experience_policy_defaults()
        self.assertTrue(defaults["use_v3_shell"])
        self.assertTrue(defaults["show_mission_strip"])
        self.assertFalse(defaults["show_mfa_nudge"])


class TenantExperiencePolicyFormTests(SimpleTestCase):
    def test_form_round_trips_v3_shell_toggle(self):
        instance = MagicMock()
        instance.cockpit_payload = {
            "tenant_experience_policy": {"use_v3_shell": False, "show_mfa_nudge": True}
        }
        form = CockpitPayloadForm(instance=instance)
        self.assertFalse(form.fields["txp_use_v3_shell"].initial)
        self.assertTrue(form.fields["txp_show_mfa_nudge"].initial)

        cleaned = form._build_payload(
            {
                "txp_use_v3_shell": False,
                "txp_show_mission_strip": True,
                "txp_hide_mission_strip_after_launch": False,
                "txp_show_experience_command_strip": True,
                "txp_show_security_posture_inline": False,
                "txp_show_mfa_nudge": True,
                "txp_show_legacy_explain_strip": False,
                "txp_show_next_action_strip": False,
                "txp_show_community_band_on_v3": False,
                "txp_show_newsletter_band_on_v3": False,
                "txp_show_proactive_help_nudge": False,
                "txp_show_lifecycle_concierge": False,
                "txp_show_kb_ai_panel": False,
                "txp_show_legacy_ai_copilot_dock": False,
                "txp_ai_layer_strip_mode": "inherit",
                "txp_ai_copilot_rail_mode": "inherit",
                "txp_sidebar_default_width": 300,
                "txp_sidebar_min_width": 200,
                "txp_sidebar_max_width": 400,
                "txp_mission_eyebrow": "Go",
                "txp_mission_cta_label": "Start",
                "txp_experience_score_label": "Ready",
                "txp_setup_surface_enabled": True,
                "txp_hidden_setup_wizard_keys": "import_csv, brand_pack",
            }
        )
        policy = cleaned["tenant_experience_policy"]
        self.assertFalse(policy["use_v3_shell"])
        self.assertTrue(policy["show_mfa_nudge"])
        self.assertEqual(policy["sidebar_default_width"], 300)
        self.assertEqual(policy["hidden_setup_wizard_keys"], ["import_csv", "brand_pack"])


class TenantExperiencePolicyChromeTests(SimpleTestCase):
    def test_v3_opt_in_mfa_nudge(self):
        request = RequestFactory().get("/")
        request.public_host_kind = "tenant"
        flags = derive_chrome_flags(request, tp_v3_tenant_shell=True)
        self.assertFalse(flags["txp_show_mfa_nudge"])
        with patch(
            "apps.siteconfig.tenant_experience_policy.resolve_tenant_experience_policy",
            return_value={**tenant_experience_policy_defaults(), "show_mfa_nudge": True},
        ):
            flags_on = derive_chrome_flags(request, tp_v3_tenant_shell=True)
        self.assertTrue(flags_on["txp_show_mfa_nudge"])

    def test_legacy_shell_shows_legacy_chrome(self):
        request = RequestFactory().get("/")
        flags = derive_chrome_flags(request, tp_v3_tenant_shell=False)
        self.assertTrue(flags["txp_show_page_explain_strip"])
        self.assertTrue(flags["txp_show_smart_action_hub"])

    def test_filter_setup_wizard_stages_hides_keys(self):
        payload = {
            "stages": [
                {
                    "key": "provision",
                    "wizards": [{"key": "import_csv"}, {"key": "brand_pack"}],
                }
            ]
        }
        filtered = filter_setup_wizard_stages(payload, hidden_keys=["import_csv"])
        wizards = filtered["stages"][0]["wizards"]
        self.assertEqual(len(wizards), 1)
        self.assertEqual(wizards[0]["key"], "brand_pack")


class TenantExperiencePolicyAccessTests(SimpleTestCase):
    def test_settings_manage_grants_configure_access(self):
        user = MagicMock()
        user.is_authenticated = True
        user.is_staff = False
        user.is_superuser = False
        user.has_feature_permission = lambda perm: perm == "settings.manage"
        self.assertTrue(user_may_configure_tenant_experience(user))


class TenantExperiencePolicyShellGateTests(SimpleTestCase):
    def test_use_v3_shell_false_disables_shell(self):
        class _Match:
            url_name = "cahier_list"
            namespace = "portal"

        request = RequestFactory().get("/")
        request.public_host_kind = "tenant"
        request.resolver_match = _Match()
        request.user = get_user_model()()  # User instances are always is_authenticated=True (read-only property)

        with patch(
            "apps.siteconfig.tenant_experience_policy.use_v3_shell_for_request",
            return_value=False,
        ):
            self.assertFalse(is_tp_v3_tenant_shell_request(request))

    def test_resolve_without_request_uses_defaults(self):
        policy = resolve_tenant_experience_policy(None)
        self.assertTrue(policy["use_v3_shell"])
