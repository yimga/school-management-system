"""Offline dual-mode bundle apply + provisioning hook."""

from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.platform_runtime.offline_mode_bundle import (
    OFFLINE_MODE_BACKEND_FLAG_UPDATES,
    apply_offline_mode_bundle_for_tenant,
    apply_offline_mode_bundle_for_school,
    merged_backend_flags_for_offline_bundle,
)
from apps.schools.models import School, is_feature_enabled


class OfflineModeBundleTests(TestCase):
    def test_merged_backend_flags_preserves_existing_keys(self):
        merged = merged_backend_flags_for_offline_bundle(
            {"enable_portal_pwa": False, "custom_flag": True}
        )
        self.assertTrue(merged["enable_offline_attendance_sync"])
        self.assertTrue(merged["enable_offline_homework_sync"])
        self.assertFalse(merged["enable_portal_pwa"])
        self.assertTrue(merged["custom_flag"])

    def test_apply_offline_mode_bundle_for_tenant(self):
        site = get_platform_site_settings_record(create=True)
        apply_offline_mode_bundle_for_tenant()
        site.refresh_from_db()
        offline = site.get_offline_runtime_settings()
        self.assertTrue(offline.get("enable_offline_mode"))
        bff = site.get_backend_feature_flags()
        self.assertTrue(bff.get("show_offline_status_bar"))
        self.assertEqual(
            bff.get("reachability_url"),
            OFFLINE_MODE_BACKEND_FLAG_UPDATES["reachability_url"],
        )

    def test_apply_offline_mode_bundle_for_school_enables_policy_module(self):
        school = School.objects.create(
            name="Policy Module School",
            slug="policy-module-school",
            subdomain="policy-module-school",
            is_active=True,
            features={},
        )
        apply_offline_mode_bundle_for_school(school)
        school.refresh_from_db()
        self.assertTrue(school.features.get("offline_mode"))
        self.assertTrue(is_feature_enabled(school, "offline_mode"))

    @override_settings(
        RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION=True,
        RMC_DEPLOYMENT_PROFILE="edge",
        RMC_HUB_BASE_URL="http://192.168.1.50:8000",
    )
    @patch("apps.platform_runtime.offline_mode_bundle.apply_offline_mode_bundle_for_school")
    def test_maybe_apply_on_provision_passes_hub_for_edge(self, mock_apply):
        from apps.platform_runtime.offline_mode_bundle import (
            maybe_apply_offline_bundle_on_provision,
        )

        school = School.objects.create(
            name="Edge Hub School",
            slug="edge-hub-school",
            subdomain="edge-hub-school",
            is_active=True,
        )
        maybe_apply_offline_bundle_on_provision(school)
        mock_apply.assert_called_once_with(
            school, hub_base_url="http://192.168.1.50:8000"
        )

    @override_settings(RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION=True)
    @patch("apps.platform_runtime.offline_mode_bundle.apply_offline_mode_bundle_for_school")
    def test_maybe_apply_on_provision_calls_apply(self, mock_apply):
        from apps.platform_runtime.offline_mode_bundle import (
            maybe_apply_offline_bundle_on_provision,
        )
        from apps.schools.models import School

        school = School.objects.create(
            name="Bundle School",
            slug="bundle-school",
            subdomain="bundle-school",
            is_active=True,
        )
        maybe_apply_offline_bundle_on_provision(school)
        mock_apply.assert_called_once()
