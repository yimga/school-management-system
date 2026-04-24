from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.platform_runtime.helpers import get_platform_site_settings_record

User = get_user_model()


class ThemeExperienceSiteNameWriteContractTests(TestCase):
    def test_apply_theme_experience_state_persists_site_name(self):
        site = get_platform_site_settings_record(create=True)

        site.apply_theme_experience_state(
            field_updates={
                "site_name": "Imported Campus",
                "primary_color": "#123456",
            },
            save=True,
        )

        site.refresh_from_db()
        self.assertEqual(site.site_name, "Imported Campus")
        self.assertEqual(site.primary_color, "#123456")


class BrandImportFromUrlViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="brand-import-admin",
            email="brand-import-admin@example.com",
            password="password",
        )
        self.client.force_login(self.user)
        self.url = reverse("siteconfig:brand_import_from_url")
        self.site = get_platform_site_settings_record(create=True)

    @patch("apps.siteconfig.brand_import.fetch_and_parse_brand_url")
    def test_brand_import_persists_site_name_and_primary_color(self, mock_fetch):
        imported_name = "Imported School " + ("X" * 200)
        mock_fetch.return_value = {
            "primary_color": "#112233",
            "site_name": imported_name,
        }

        response = self.client.post(
            self.url,
            {
                "consent": "1",
                "url": "https://example.com",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.site.refresh_from_db()
        self.assertEqual(self.site.primary_color, "#112233")
        self.assertEqual(self.site.site_name, imported_name[:120])
