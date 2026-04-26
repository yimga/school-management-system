"""Control plane sidebar must expose admin-sidebar parity links (manager host)."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, SimpleTestCase

from apps.schools.control_plane_nav import build_control_plane_nav


class ControlPlaneNavParityTests(SimpleTestCase):
    databases = {"default"}

    def test_platform_settings_group_includes_admin_parity_ids(self):
        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        User = get_user_model()
        request.user = User(is_superuser=True, username="nav_parity")
        groups = build_control_plane_nav(request)
        all_ids = []
        for grp in groups:
            for it in grp.get("items") or []:
                all_ids.append(it.get("id"))
        required = {
            "super_platform_operator_hub",
            "super_operator_policy",
            "super_backlog_unlock_center",
            "super_fleet_governed_changes",
            "config_console",
            "cp_tenant_runtime_hub",
            "cp_region_grading_scales",
            "cp_region_validation",
            "cp_region_comparison",
            "cp_theme_experience",
            "cp_feature_control",
            "cp_metadata_operator_hub",
            "cp_entity_catalog",
            "cp_metadata_dynamic_fields",
            "cp_config_mutation_audit_evidence",
            "cp_platform_backoffice",
            "cp_admin_bridge_integrations",
            "cp_admin_bridge_marketplace_apps",
            "cp_admin_bridge_packages_installed",
            "cp_admin_bridge_experience_packs",
            "cp_admin_bridge_runtime_defaults",
            "cp_admin_bridge_phase_b_domain_snapshots",
            "cp_admin_bridge_ai_model_registry",
            "cp_admin_bridge_global_brand_registry",
            "cp_admin_bridge_platform_global_branding",
            "cp_report_library",
        }
        missing = required - set(all_ids)
        self.assertFalse(
            missing,
            msg="Control plane nav missing admin-parity entries: %s. Got ids: %s"
            % (missing, sorted(all_ids)),
        )
        # One SIS / LMS lives under Integrations only (not duplicated under Platform settings).
        self.assertIn(
            "super_one_sis_any_lms",
            all_ids,
            msg="Integrations entry super_one_sis_any_lms must remain in sidebar",
        )

    def test_support_success_group_includes_csat_link(self):
        request = RequestFactory().get("/super/support/")
        request.urlconf = "config.manager_urls"
        User = get_user_model()
        request.user = User(is_superuser=True, username="nav_csat")
        groups = build_control_plane_nav(request)
        support_group = next(
            (g for g in groups if g.get("label") == "Support & Success"), None
        )
        self.assertIsNotNone(support_group)
        ids = {it["id"] for it in support_group.get("items") or []}
        self.assertIn("super_support", ids)
        self.assertIn("super_support_csat", ids)
