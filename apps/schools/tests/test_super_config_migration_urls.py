"""
Final verification: all Admin→Super migration URLs resolve and return 200 (no 500).
RUNBOOK_ADMIN_TO_SUPER_MIGRATION final checklist. Requires superuser on manager host.
"""
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class SuperConfigMigrationUrlTests(TestCase):
    """Verify every new super config URL returns 200 for superuser on manager host."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="super_verify",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"

    def _get(self, url_name, args=None, kwargs=None, query=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        url = reverse(url_name, args=args, kwargs=kwargs)
        if query:
            url = f"{url}?{query}"
        return self.client.get(url, HTTP_HOST=self.host)

    def test_config_hub_200(self):
        response = self._get("super:config_hub")
        self.assertEqual(response.status_code, 200, "Config hub must return 200")

    def test_site_settings_list_200(self):
        response = self._get("super:site_settings_list")
        self.assertEqual(response.status_code, 200, "Site settings list must return 200")

    def test_regions_list_200(self):
        response = self._get("super:regions_list")
        self.assertEqual(response.status_code, 200, "Regions list must return 200")

    def test_grading_list_200(self):
        response = self._get("super:grading_list")
        self.assertEqual(response.status_code, 200, "Grading list must return 200")

    def test_plans_list_200(self):
        response = self._get("super:plans_list")
        self.assertEqual(response.status_code, 200, "Plans list must return 200")

    def test_feature_toggles_list_200(self):
        response = self._get("super:feature_toggles_list")
        self.assertEqual(response.status_code, 200, "Feature toggles list must return 200")

    def test_schools_list_200(self):
        response = self._get("super:schools_list")
        self.assertEqual(response.status_code, 200, "Schools list must return 200")

    def test_schools_list_pagination_and_filters(self):
        response = self._get("super:schools_list", query="page=1&is_active=1&q=test&country_code=US")
        self.assertEqual(response.status_code, 200, "Schools list with filters must return 200")

    def test_site_settings_edit_200_or_404(self):
        # Edit requires existing pk; 404 if no SiteSettings
        from apps.siteconfig.models import SiteSettings
        first = SiteSettings.objects.first()
        if first:
            response = self._get("super:site_settings_edit", kwargs={"pk": first.pk})
            self.assertEqual(response.status_code, 200, "Site settings edit must return 200 when pk exists")
        else:
            response = self._get("super:site_settings_edit", kwargs={"pk": 1})
            self.assertEqual(response.status_code, 404, "Site settings edit must return 404 when pk missing")

    def test_ai_model_hub_200(self):
        response = self._get("super:ai_model_hub")
        self.assertEqual(response.status_code, 200, "AI model hub must return 200")

    def test_incidents_list_200(self):
        response = self._get("super:incidents_list")
        self.assertEqual(response.status_code, 200, "Incidents list must return 200")

    def test_billing_accounts_list_200(self):
        response = self._get("super:billing_accounts_list")
        self.assertEqual(response.status_code, 200, "Billing accounts list must return 200")

    def test_migration_runs_list_200(self):
        response = self._get("super:migration_runs_list")
        self.assertEqual(response.status_code, 200, "Migration runs list must return 200")
