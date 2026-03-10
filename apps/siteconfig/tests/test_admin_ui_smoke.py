from django.contrib.auth import get_user_model
from html.parser import HTMLParser
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from urllib.parse import urlsplit

from apps.accounts.models import Permission
from apps.siteconfig.models import SiteSettings
from apps.siteconfig.context_processors import site_settings


User = get_user_model()


class _SidebarLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attr_map = dict(attrs)
        classes = attr_map.get("class", "")
        href = attr_map.get("href")
        if not href:
            return
        if "admin-sidebar-link" in classes or "admin-sidebar-model-link" in classes:
            self.links.append(href)


class AdminUiSmokeTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.get_solo()
        self.factory = RequestFactory()
        # Keep admin smoke assertions on the base-domain admin path.
        # Tenant middleware redirects /admin/* on tenant hosts to backend.
        self.client.defaults["HTTP_HOST"] = "localhost"
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
        # Settings manager should see Site settings link (change or changelist depending on SITE in context)
        change_url = reverse("admin:siteconfig_sitesettings_change", args=[self.site.pk])
        changelist_url = reverse("admin:siteconfig_sitesettings_changelist")
        self.assertTrue(
            change_url in html or changelist_url in html,
            msg=f"Expected Site settings link (change or changelist) in HTML for settings manager",
        )

    def test_admin_sidebar_child_links_are_resolvable(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 200)

        parser = _SidebarLinkParser()
        parser.feed(response.content.decode("utf-8", errors="ignore"))

        sidebar_paths = []
        for href in parser.links:
            parsed = urlsplit(href)
            if parsed.scheme or parsed.netloc:
                continue
            if not parsed.path.startswith("/"):
                continue
            if parsed.path.startswith("/static/") or parsed.path.startswith("/media/"):
                continue
            if parsed.fragment:
                continue
            normalized = parsed.path
            if parsed.query:
                normalized = f"{normalized}?{parsed.query}"
            sidebar_paths.append(normalized)

        # Keep order but remove duplicates.
        sidebar_paths = list(dict.fromkeys(sidebar_paths))
        self.assertGreaterEqual(
            len(sidebar_paths),
            12,
            msg=f"Unexpectedly few sidebar links collected: {sidebar_paths}",
        )

        quick_paths = {
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
        }
        child_paths = [
            path
            for path in sidebar_paths
            if path.startswith("/admin/") and path not in quick_paths
        ]
        self.assertTrue(
            child_paths,
            msg=f"No child admin links discovered in sidebar output: {sidebar_paths}",
        )

        failures = []
        for path in sidebar_paths:
            page = self.client.get(path)
            if page.status_code not in (200, 302, 403):
                failures.append((path, page.status_code))
        self.assertFalse(failures, msg=f"Broken sidebar links detected: {failures}")

    def test_admin_dashboard_legacy_path_redirects_to_index(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/admin/dashboard/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:index"))
