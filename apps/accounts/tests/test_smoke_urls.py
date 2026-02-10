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

    def test_admin_index(self):
        self.assertEqual(reverse("admin:index"), "/admin/")

    def test_accounts_login(self):
        self.assertEqual(reverse("accounts:login"), "/authentication/login/")

    def test_siteconfig_customizer(self):
        self.assertEqual(reverse("siteconfig:customizer"), "/siteconfig/customizer/")

    def test_siteconfig_user_preferences(self):
        self.assertEqual(reverse("siteconfig:user_preferences"), "/siteconfig/preferences/")

    def test_siteconfig_clear_preview(self):
        self.assertEqual(reverse("siteconfig:clear_preview"), "/siteconfig/customizer/clear-preview/")

    def test_siteconfig_feature_control_panel(self):
        self.assertEqual(reverse("siteconfig:feature_control_panel"), "/siteconfig/feature-control/")

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
        self.assertEqual(reverse("accounts:backend_dashboard"), "/authentication/backend/")

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

    def test_admin_siteconfig_changelist(self):
        self.assertEqual(reverse("admin:siteconfig_sitesettings_changelist"), "/admin/siteconfig/sitesettings/")

    def test_admin_siteconfig_change_with_pk(self):
        url = reverse("admin:siteconfig_sitesettings_change", args=[1])
        self.assertEqual(url, "/admin/siteconfig/sitesettings/1/change/")
