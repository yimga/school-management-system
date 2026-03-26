"""
Smoke tests for URL resolution. Use SimpleTestCase so no database is created.
CI can run: python manage.py test apps.accounts.tests.test_smoke_urls
even when the DB is missing or broken.
"""

from django.test import SimpleTestCase
from django.urls import reverse


class SmokeUrlResolutionTests(SimpleTestCase):
    """Reverse critical URL names; no DB required."""

    def test_home(self):
        self.assertEqual(reverse("home"), "/")

    def test_health(self):
        self.assertEqual(reverse("health"), "/health/")

    def test_healthz(self):
        self.assertEqual(reverse("healthz"), "/healthz/")

    def test_ready(self):
        self.assertEqual(reverse("ready"), "/ready/")

    def test_status(self):
        self.assertEqual(reverse("status"), "/status/")

    def test_admin_index(self):
        self.assertEqual(reverse("admin:index"), "/admin/")

    def test_accounts_login(self):
        self.assertEqual(reverse("accounts:login"), "/authentication/login/")

    def test_accounts_root(self):
        self.assertEqual(reverse("accounts:root"), "/authentication/")

    def test_studio_os_experience(self):
        """Legacy customizer → Studio OS Experience (legacy path removals)."""
        self.assertEqual(reverse("studio_os:experience"), "/studio/experience/")

    def test_siteconfig_user_preferences(self):
        self.assertEqual(
            reverse("siteconfig:user_preferences"), "/siteconfig/preferences/"
        )

    def test_siteconfig_clear_preview(self):
        self.assertEqual(
            reverse("siteconfig:clear_preview"), "/siteconfig/customizer/clear-preview/"
        )

    def test_siteconfig_feature_control_panel(self):
        self.assertEqual(
            reverse("siteconfig:feature_control_panel"), "/siteconfig/feature-control/"
        )

    def test_portal_parent_dashboard(self):
        self.assertEqual(reverse("portal:parent_dashboard"), "/portal/parent/")

    def test_analytics_dashboard(self):
        self.assertEqual(reverse("analytics:dashboard"), "/analytics/")

    def test_analytics_master_sheet(self):
        self.assertEqual(reverse("analytics:master_sheet"), "/analytics/master-sheet/")

    def test_reports_publish_term_results(self):
        self.assertEqual(reverse("reports:publish_term_results"), "/reports/publish/")

    def test_evals_teacher_dashboard(self):
        self.assertEqual(reverse("evals:teacher_dashboard"), "/evals/teacher/")

    def test_backend_dashboard(self):
        """Frontend admin: canonical URL is under authentication."""
        self.assertEqual(
            reverse("accounts:backend_dashboard"), "/authentication/backend/"
        )

    def test_admin_dashboard(self):
        """No-regression: admin dashboard (obs) path."""
        self.assertEqual(reverse("admin_dashboard"), "/admin/dashboard/")

    def test_api_admin_weather(self):
        self.assertEqual(reverse("api_admin_weather"), "/api/admin/weather/")

    def test_api_weather_context(self):
        self.assertEqual(reverse("api_weather_context"), "/api/weather/context/")

    def test_six_critical_paths_resolve(self):
        """Plan Phase 0: all six critical URLs must resolve."""
        critical = [
            ("admin:index", "/admin/"),
            ("accounts:login", "/authentication/login/"),
            ("portal:parent_dashboard", "/portal/parent/"),
            ("evals:teacher_dashboard", "/evals/teacher/"),
            ("accounts:backend_dashboard", "/authentication/backend/"),
        ]
        for name, expected_path in critical:
            with self.subTest(url_name=name):
                self.assertEqual(reverse(name), expected_path)

    def test_finance_dashboard(self):
        self.assertEqual(reverse("finance:dashboard"), "/finance/")

    def test_super_site_settings_list_path(self):
        """SiteSettings removed from platform admin; list is on control plane."""
        self.assertEqual(
            reverse("super:site_settings_list"),
            "/super/config/site-settings/",
        )

    def test_super_site_settings_edit_path(self):
        self.assertEqual(
            reverse("super:site_settings_edit", kwargs={"pk": 1}),
            "/super/config/site-settings/1/",
        )

    def test_marketing_blog_detail(self):
        """Blog post links (e.g. marketing_page.html) resolve on root urlconf."""
        url = reverse("marketing_blog_detail", kwargs={"slug": "my-post"})
        self.assertEqual(url, "/blog/my-post/")

    def test_analytics_deadlines(self):
        self.assertEqual(reverse("analytics:deadlines"), "/analytics/deadlines/")

    def test_marketing_book_demo(self):
        self.assertEqual(reverse("marketing_book_demo"), "/book-demo/")

    def test_global_login_discovery(self):
        self.assertEqual(reverse("global_login_discovery"), "/discover/")

    def test_public_support_hub(self):
        self.assertEqual(reverse("public_support_hub"), "/support/")

    def test_public_verify_hub(self):
        self.assertEqual(reverse("public_verify_hub"), "/verify/")

    def test_studio_experience(self):
        self.assertEqual(reverse("studio_os:experience"), "/studio/experience/")

    def test_siteconfig_dashboard_hub(self):
        self.assertEqual(
            reverse("siteconfig:dashboard_hub"), "/siteconfig/dashboard-hub/"
        )

    def test_compliance_dashboard(self):
        self.assertEqual(reverse("compliance:dashboard"), "/compliance/dashboard/")

    def test_communication_groups(self):
        self.assertEqual(reverse("communication:group_list"), "/communication/groups/")

    # Phase H: control plane and Studio OS URL names must resolve (no 404 from misconfiguration)
    def test_super_dashboard_resolves(self):
        self.assertEqual(reverse("super:dashboard"), "/super/")

    def test_super_trust_center_resolves(self):
        """§3.2.2 Phase 8: control-plane trust hub URL must reverse."""
        self.assertEqual(reverse("super:trust_center"), "/super/trust/")

    def test_super_ai_gateway_console_resolves(self):
        """Control plane: consolidated JSON consoles for API-only AI endpoints."""
        self.assertEqual(
            reverse("super:ai_gateway_console"),
            "/super/ai-gateway-console/",
        )

    def test_super_billing_and_trust_paths_resolve(self):
        """Primary nav uses these prefixes for Analytics (billing) and Home (trust)."""
        self.assertEqual(reverse("super:billing_dashboard"), "/super/billing/")
        self.assertEqual(reverse("super:trust_center"), "/super/trust/")
        self.assertEqual(reverse("super:compliance_overview"), "/super/compliance/")

    def test_tenant_security_trust_hub_resolves(self):
        """§3.2.2 Phase 8: tenant Security & trust hub."""
        self.assertEqual(
            reverse("accounts:security_trust_hub"),
            "/authentication/backend/security-trust/",
        )

    def test_tenant_impersonation_audit_resolves(self):
        """§3.2.2 Phase 8: school-scoped impersonation audit."""
        self.assertEqual(
            reverse("accounts:tenant_impersonation_audit"),
            "/authentication/backend/security-trust/impersonation/",
        )

    def test_tenant_app_catalog_resolves(self):
        """§3.2.3 Phase 9: tenant marketplace catalog (tenant urlconf)."""
        self.assertEqual(
            reverse("tenant_app_catalog", urlconf="config.tenant_urls"),
            "/settings/app-catalog/",
        )

    def test_backend_teacher_detail_resolves(self):
        """People backend: teacher detail linked from backend_teacher_list."""
        url = reverse("accounts:backend_teacher_detail", kwargs={"teacher_id": 1})
        self.assertTrue(
            url.startswith("/authentication/backend/teachers/"),
            msg=url,
        )
        self.assertIn("1", url)

    def test_studio_os_all_modes_resolve(self):
        """Studio OS shell and all five mode URLs must reverse correctly."""
        modes = [
            ("studio_os:shell", "/studio/"),
            ("studio_os:experience", "/studio/experience/"),
            ("studio_os:automation", "/studio/automation/"),
            ("studio_os:output", "/studio/output/"),
            ("studio_os:launch", "/studio/launch/"),
            ("studio_os:control", "/studio/control/"),
        ]
        for name, expected in modes:
            with self.subTest(url_name=name):
                self.assertEqual(reverse(name), expected)

    def test_all_ai_gateway_api_paths_resolve(self):
        """Every productized AI gateway route under namespace api: must reverse (registry + UI cards)."""
        expected = {
            "api:ai-setup-assistant": "/api/ai/setup-assistant/",
            "api:ai-workflow-draft": "/api/ai/workflow-draft/",
            "api:ai-policy-explain": "/api/ai/policy-explain/",
            "api:ai-document-classify": "/api/ai/document-classify/",
            "api:ai-semantic-search": "/api/ai/semantic-search/",
            "api:ai-migration-suggest": "/api/ai/migration-suggest/",
            "api:ai-admin-copilot": "/api/ai/admin-copilot/",
            "api:ai-theme-recommend": "/api/ai/theme-recommend/",
            "api:ai-feature-control-explain": "/api/ai/feature-control-explain/",
            "api:ai-report-recommend": "/api/ai/report-recommend/",
            "api:ai-design-studio-draft": "/api/ai/design-studio-draft/",
            "api:ai-live-preview-explain": "/api/ai/live-preview-explain/",
            "api:ai-system-config-explain": "/api/ai/system-config-explain/",
            "api:ai-dashboard-pack-recommend": "/api/ai/dashboard-pack-recommend/",
            "api:ai-support-assistant": "/api/ai/support-assistant/",
            "api:ai-tenant-maturity": "/api/ai/tenant-maturity/",
            "api:ai-data-quality-assistant": "/api/ai/data-quality-assistant/",
            "api:ai-marketplace-recommend": "/api/ai/marketplace-recommend/",
            "api:ai-control-plane-intelligence": "/api/ai/control-plane-intelligence/",
            "api:ai-interop-assistant": "/api/ai/interop-assistant/",
            "api:ai-runtime-config-explain": "/api/ai/runtime-config-explain/",
            "api:ai-observability-assistant": "/api/ai/observability-assistant/",
            "api:ai-billing-usage-explain": "/api/ai/billing-usage-explain/",
            "api:ai-trust-compliance-assistant": "/api/ai/trust-compliance-assistant/",
            "api:ai-studio-os-assistant": "/api/ai/studio-os-assistant/",
            "api:ai-feedback": "/api/ai/feedback/",
        }
        for name, path in expected.items():
            with self.subTest(url_name=name):
                self.assertEqual(reverse(name), path)
