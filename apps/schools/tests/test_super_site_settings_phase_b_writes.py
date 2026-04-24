"""Phase B: super control-plane tenant settings maintenance uses apply_feature_control_state."""

from __future__ import annotations

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.helpers import get_platform_site_settings_record


@override_settings(ALLOWED_HOSTS=["*"])
class SuperSiteSettingsPhaseBWritesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="super_phase_b_writes",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_super_site_settings_edit_saves_maintenance_via_apply_feature_control_state(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.apply_feature_control_state(field_updates={"maintenance_mode": False})
        site.refresh_from_db()
        self.assertFalse(site.maintenance_mode)

        url = reverse("super:site_settings_edit", kwargs={"pk": site.pk})
        response = self.client.post(
            url,
            data={
                "maintenance_mode": "on",
                "theme_pack": "",
                "admin_theme_pack": "",
                "teacher_theme_pack": "",
                "parent_theme_pack": "",
                "default_term_report_style": "",
                "default_annual_report_style": "",
            },
            HTTP_HOST=self.host,
            follow=False,
        )
        self.assertEqual(response.status_code, 302, response.content)

        site.refresh_from_db()
        self.assertTrue(site.maintenance_mode)
