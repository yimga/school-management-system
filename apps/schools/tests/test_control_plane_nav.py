"""Control plane sidebar must expose admin-sidebar parity links (manager host)."""

from django.test import RequestFactory, SimpleTestCase

from apps.schools.control_plane_nav import build_control_plane_nav


class ControlPlaneNavParityTests(SimpleTestCase):
    databases = {"default"}

    def test_platform_settings_group_includes_admin_parity_ids(self):
        request = RequestFactory().get("/super/")
        request.urlconf = "config.manager_urls"
        groups = build_control_plane_nav(request)
        all_ids = []
        for grp in groups:
            for it in grp.get("items") or []:
                all_ids.append(it.get("id"))
        required = {
            "super_platform_operator_hub",
            "config_console",
            "cp_theme_experience",
            "cp_feature_control",
            "cp_platform_backoffice",
            "cp_integrations_super",
            "cp_report_library",
        }
        missing = required - set(all_ids)
        self.assertFalse(
            missing,
            msg="Control plane nav missing admin-parity entries: %s. Got ids: %s"
            % (missing, sorted(all_ids)),
        )
