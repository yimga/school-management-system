"""Control plane sidebar must expose admin-sidebar parity links (manager host)."""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, SimpleTestCase, override_settings

from apps.schools.control_plane_nav import (
    build_control_plane_nav,
    build_manager_platform_admin_nav,
)
from apps.schools.super_admin_bridge_registry import (
    PLATFORM_ADMIN_BRIDGE_ORDER,
    PLATFORM_ADMIN_BRIDGES,
)


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

    def test_advanced_group_uses_direct_admin_urls(self):
        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        User = get_user_model()
        request.user = User(is_superuser=True, username="nav_advanced")
        groups = build_control_plane_nav(request)
        advanced = next((g for g in groups if g.get("label") == "Advanced"), None)
        self.assertIsNotNone(advanced)
        for item in advanced.get("items") or []:
            self.assertTrue(item.get("url"), msg=item.get("id"))
            self.assertNotIn("/super/admin-bridge/", item["url"], msg=item.get("id"))
        bridge_ids = {
            meta["nav_id"]
            for key in PLATFORM_ADMIN_BRIDGE_ORDER
            if (meta := PLATFORM_ADMIN_BRIDGES.get(key)) and meta.get("show_in_nav")
        }
        nav_ids = {it["id"] for it in advanced.get("items") or []}
        self.assertTrue(bridge_ids.issubset(nav_ids), bridge_ids - nav_ids)

    def test_advanced_group_expands_when_admin_changelist_active(self):
        request = RequestFactory().get("/admin/integrations_marketplace/integration/")
        request.urlconf = "config.manager_urls"
        User = get_user_model()
        request.user = User(is_superuser=True, username="nav_advanced_expand")
        groups = build_control_plane_nav(request)
        advanced = next((g for g in groups if g.get("label") == "Advanced"), None)
        self.assertIsNotNone(advanced)
        self.assertTrue(advanced.get("expanded"))
        current = [it for it in advanced.get("items") or [] if it.get("is_current")]
        self.assertTrue(current, msg="expected a current Advanced nav item on admin path")

    def test_manager_platform_admin_nav_quick_links(self):
        request = RequestFactory().get("/admin/")
        request.urlconf = "config.manager_urls"
        User = get_user_model()
        request.user = User(is_superuser=True, username="nav_mgr_admin")
        nav = build_manager_platform_admin_nav(request)
        ids = {row["id"] for row in nav.get("quick_links") or []}
        self.assertIn("admin_index", ids)
        self.assertIn("super_dashboard", ids)
        self.assertIn("super_platform_operator_hub", ids)
        guided_ids = {row["id"] for row in nav.get("guided_links") or []}
        self.assertIn("config_center", guided_ids)
        self.assertIn("configuration_center", guided_ids)
        self.assertIn("studio_shell", guided_ids)


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.manager_urls")
class ControlPlaneAdvancedNavHttpTests(SimpleTestCase):
    databases = {"default"}

    def test_advanced_nav_items_return_ok_on_manager_host(self):
        User = get_user_model()
        user = User(is_superuser=True, is_staff=True, username="adv_http")
        client = Client()
        client.force_login(user)
        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        request.user = user
        advanced = next(
            (
                g
                for g in build_control_plane_nav(request)
                if g.get("label") == "Advanced"
            ),
            None,
        )
        self.assertIsNotNone(advanced)
        sample = list(advanced.get("items") or [])[:3]
        self.assertGreaterEqual(len(sample), 2)
        for item in sample:
            with self.subTest(nav_id=item.get("id")):
                response = client.get(
                    item["url"],
                    HTTP_HOST="manager.runmycampus.com",
                    follow=False,
                )
                self.assertIn(
                    response.status_code,
                    (200, 302),
                    msg=f"{item.get('id')} -> {item.get('url')}",
                )
