from django.contrib.auth import get_user_model
from html.parser import HTMLParser
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from urllib.parse import urlsplit

from apps.accounts.models import Permission
from apps.platform_runtime.helpers import get_platform_site_settings_record
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
        self.site = get_platform_site_settings_record(create=True)
        self.factory = RequestFactory()
        # Keep admin smoke assertions on the public/local admin path.
        # Tenant hosts redirect /admin/* to the backend console, while local
        # development may render the platform shell directly.
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
        content = response.content.decode("utf-8", errors="ignore")

        platform_quick_link = reverse("super:dashboard")
        tenant_quick_link = reverse("accounts:backend_dashboard")

        if platform_quick_link in content:
            self.assertContains(response, platform_quick_link)
            self.assertContains(response, "Control plane")
            quick_paths = [
                reverse("admin:index"),
                platform_quick_link,
                reverse("super:site_settings_edit", kwargs={"pk": self.site.pk}),
                reverse("super:regions_list"),
                reverse("admin:integrations_marketplace_integration_changelist"),
                reverse("siteconfig:feature_control_panel"),
                reverse("siteconfig:theme_colors"),
                reverse("studio_os:output"),
                reverse("super:blueprint_marketplace"),
                reverse("manager_help"),
            ]
        else:
            self.assertContains(response, tenant_quick_link)
            self.assertContains(response, "Backend Console")
            quick_paths = [
                reverse("admin:index"),
                reverse("admin:siteconfig_sitesettings_change", args=[self.site.pk]),
                reverse("super:regions_list"),
                reverse("admin:integrations_marketplace_integration_changelist"),
                reverse("siteconfig:feature_control_panel"),
                reverse("siteconfig:theme_colors"),
                reverse("studio_os:output"),
                reverse("kb:kb_home"),
                reverse("portal:document_library_manage"),
                tenant_quick_link,
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
        request.public_host_kind = "manager"  # so context builds CONTROL_PLANE_NAV
        request.urlconf = "config.manager_urls"  # match control_plane_nav resolution
        ctx = site_settings(request)
        # Settings manager should get CAN_MANAGE_SETTINGS and a config/settings entry in control plane nav
        self.assertTrue(
            ctx.get("CAN_MANAGE_SETTINGS") is True,
            msg="Expected CAN_MANAGE_SETTINGS True for settings manager",
        )
        nav_has_config_entry = False
        for grp in ctx.get("CONTROL_PLANE_NAV") or []:
            for it in grp.get("items") or []:
                if it.get("url") and (
                    it.get("id") == "config_console"
                    or (it.get("label") or "").lower().find("config") >= 0
                ):
                    nav_has_config_entry = True
                    break
            if nav_has_config_entry:
                break
        self.assertTrue(
            nav_has_config_entry,
            msg="Expected System config or Site settings entry in control plane nav for settings manager",
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
            reverse("super:dashboard"),
            reverse("super:platform_operator_hub"),
            reverse("super:site_settings_edit", kwargs={"pk": self.site.pk}),
            reverse("super:regions_list"),
            reverse("admin:integrations_marketplace_integration_changelist"),
            reverse("siteconfig:feature_control_panel"),
            reverse("siteconfig:theme_colors"),
            reverse("studio_os:output"),
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
