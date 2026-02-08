from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission
from apps.siteconfig.models import SiteSettings
from apps.siteconfig.context_processors import site_settings


User = get_user_model()


class AdminUiSmokeTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.get_solo()
        self.factory = RequestFactory()
        self.superuser = User.objects.create_superuser(
            username="admin-ui-super",
            email="admin-ui-super@example.com",
            password="password",
        )

    def test_admin_quick_access_links_are_resolvable(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin-sidebar-quick-access")
        self.assertContains(response, reverse("accounts:backend_dashboard"))
        self.assertContains(response, "Back to Backend")

        quick_paths = [
            reverse("admin:index"),
            reverse("admin:siteconfig_sitesettings_change", args=[self.site.pk]),
            reverse("admin:siteconfig_regionconfig_changelist"),
            reverse("admin:siteconfig_integration_changelist"),
            reverse("siteconfig:feature_control_panel"),
            reverse("siteconfig:theme_colors"),
            reverse("siteconfig:report_library"),
            reverse("kb:kb_home"),
            reverse("portal:document_library_manage"),
            reverse("accounts:backend_dashboard"),
        ]

        for path in quick_paths:
            page = self.client.get(path)
            self.assertIn(
                page.status_code,
                (200, 302, 403),
                msg=f"Unexpected status for quick link {path}: {page.status_code}",
            )

    def test_admin_quick_access_visible_for_settings_manager(self):
        manager = User.objects.create_user(
            username="admin-ui-manager",
            email="admin-ui-manager@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        manager.is_staff = True
        manager.save(update_fields=["is_staff"])
        perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        manager.feature_permissions.add(perm)

        request = self.factory.get("/admin/")
        request.user = manager
        request.session = {}
        ctx = site_settings(request)
        html = render_to_string("admin/app_list.html", {"app_list": [], **ctx}, request=request)
        self.assertIn(reverse("admin:siteconfig_sitesettings_change", args=[self.site.pk]), html)
