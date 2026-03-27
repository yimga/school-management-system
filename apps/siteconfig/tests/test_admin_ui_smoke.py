import unittest
from datetime import date
from html.parser import HTMLParser
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse, set_urlconf

from apps.accounts.models import Permission
from apps.compliance.models import ComplianceRule, LegalDocument
from apps.global_registries.models import RegionConfig
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.siteconfig.context_processors import site_settings
from apps.integrations_marketplace.models import Integration
from apps.portal.models import Announcement, PortalFeatureItem
from apps.runtime_blueprints.models import DashboardWidget
from apps.siteconfig.models import ReportCardStyle, SiteSettings
from apps.siteconfig.models_dashboard import DashboardUserPreference
from apps.siteconfig.tests.test_admin import _admin_request_with_session_and_messages
from config.admin import tenant_admin_site


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
    def _client_get_or_skip_stale_workflow_schema(self, path):
        """Avoid hard failures when a reused SQLite test DB predates WorkflowTemplate.certified (0135+)."""
        try:
            return self.client.get(path)
        except OperationalError as exc:
            msg = str(exc).lower()
            if "workflowtemplate" in msg and "certified" in msg:
                raise unittest.SkipTest(
                    "Test DB missing siteconfig_workflowtemplate.certified — apply migrations "
                    "(≥ siteconfig.0135_workflow_template_certified_version) or recreate the pytest database."
                ) from exc
            raise

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
            page = self._client_get_or_skip_stale_workflow_schema(path)
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
            msg="Expected Config center or Site settings entry in control plane nav for settings manager",
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
            page = self._client_get_or_skip_stale_workflow_schema(path)
            if page.status_code not in (200, 302, 403):
                failures.append((path, page.status_code))
        self.assertFalse(failures, msg=f"Broken sidebar links detected: {failures}")

    def test_admin_dashboard_legacy_path_redirects_to_index(self):
        self.client.force_login(self.superuser)
        response = self.client.get("/admin/dashboard/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("admin:index"))

    def test_sitesettings_change_form_links_to_control_plane_surfaces(self):
        """P3: admin SiteSettings is not the only story — escape hatch points to product shells."""
        # TenantMiddleware redirects Client GET /admin/… on tenant hosts to the backend shell; exercise
        # tenant_admin_site.change_view via RequestFactory (see apps/siteconfig/tests/test_admin.py).
        # Admin's reverse() uses get_urlconf() (thread-local), not request.urlconf — set tenant URLconf
        # so admin:app_list includes registered apps (e.g. accounts) on this AdminSite instance.
        model_admin = tenant_admin_site._registry[SiteSettings]
        path = reverse(
            "admin:siteconfig_sitesettings_change",
            args=[self.site.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(self.site.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("site-settings-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:theme_colors"),
                reverse("siteconfig:feature_control_panel"),
                reverse("siteconfig:console_domains_hub"),
                reverse("studio_os:output"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)
    def test_reportcardstyle_change_form_links_to_control_plane_surfaces(self):
        """P3: ReportCardStyle admin links to report builder + Output studio + config hub (tenant-safe URLs)."""
        style = ReportCardStyle.objects.create(
            name="Admin UI smoke report style",
            slug="admin-ui-smoke-report-style",
        )
        model_admin = tenant_admin_site._registry[ReportCardStyle]
        path = reverse(
            "admin:siteconfig_reportcardstyle_change",
            args=[style.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(style.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("reportcard-style-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:reportcard_builder"),
                reverse("studio_os:output"),
                reverse("siteconfig:console_domains_hub"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)
    def test_dashboardwidget_change_form_links_to_control_plane_surfaces(self):
        """P3: runtime_blueprints DashboardWidget change form → dashboard hubs + Studio visual packs."""
        widget = DashboardWidget.objects.create(
            id="p3-admin-smoke-widget",
            name="P3 admin smoke widget",
            description="Control-plane escape hatch test",
            widget_type="stats",
            template_path="dashboard/widgets/smoke.html",
            page="backend",
        )
        model_admin = tenant_admin_site._registry[DashboardWidget]
        path = reverse(
            "admin:runtime_blueprints_dashboardwidget_change",
            args=[widget.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(widget.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("dashboard-widget-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:dashboard_configuration_hub"),
                reverse("siteconfig:dashboard_hub"),
                reverse("studio_os:experience_dashboard_visual_packs"),
                reverse("siteconfig:console_domains_hub"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)

    def test_dashboarduserpreference_change_form_links_to_control_plane_surfaces(self):
        """P3: siteconfig DashboardUserPreference → user preferences + dashboard hubs."""
        pref, _ = DashboardUserPreference.objects.get_or_create(user=self.superuser)
        model_admin = tenant_admin_site._registry[DashboardUserPreference]
        path = reverse(
            "admin:siteconfig_dashboarduserpreference_change",
            args=[pref.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(pref.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("dashboard-user-pref-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:user_preferences"),
                reverse("siteconfig:dashboard_configuration_hub"),
                reverse("studio_os:experience_dashboard_visual_packs"),
                reverse("siteconfig:console_domains_hub"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)
    def test_integration_change_form_links_to_control_plane_surfaces(self):
        """P3: integrations_marketplace Integration → feature control + API Center."""
        integration = Integration.objects.create(
            name="P3 admin smoke integration",
            slug="p3-admin-smoke-integration",
            provider="email",
        )
        model_admin = tenant_admin_site._registry[Integration]
        path = reverse(
            "admin:integrations_marketplace_integration_change",
            args=[integration.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(integration.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("integration-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:feature_control_panel"),
                reverse("apicenter:dashboard"),
                reverse("siteconfig:console_domains_hub"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)

    def test_compliancerule_change_form_links_to_control_plane_surfaces(self):
        """P3: compliance ComplianceRule admin → configuration hub + feature control + KB."""
        rule = ComplianceRule.objects.create(
            name="Admin UI smoke compliance rule",
            rule_type="privacy_policy",
            description="Smoke test rule for escape hatch links.",
        )
        model_admin = tenant_admin_site._registry[ComplianceRule]
        path = reverse(
            "admin:compliance_compliancerule_change",
            args=[rule.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(rule.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("compliance-rule-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:console_domains_hub"),
                reverse("siteconfig:feature_control_panel"),
                reverse("kb:kb_home"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)

    def test_legaldocument_change_form_links_to_control_plane_surfaces(self):
        """P3: compliance LegalDocument admin → same product shells as other governance admins."""
        region = RegionConfig.objects.create(
            code="ADM",
            name="Admin smoke region",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        doc = LegalDocument.objects.create(
            region=region,
            document_type="privacy_policy",
            title="Admin UI smoke legal doc",
            content="Smoke content.",
            effective_date=date(2026, 1, 1),
        )
        model_admin = tenant_admin_site._registry[LegalDocument]
        path = reverse(
            "admin:compliance_legaldocument_change",
            args=[doc.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(doc.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("legal-document-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:console_domains_hub"),
                reverse("siteconfig:feature_control_panel"),
                reverse("kb:kb_home"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)

    def test_portalfeatureitem_change_form_links_to_control_plane_surfaces(self):
        """P3: portal document library items → library + feature control + Studio Output."""
        item = PortalFeatureItem.objects.create(
            feature="documents",
            title="Admin UI smoke portal feature item",
        )
        model_admin = tenant_admin_site._registry[PortalFeatureItem]
        path = reverse(
            "admin:portal_portalfeatureitem_change",
            args=[item.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(item.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-feature-item-cp-escape-heading", body)
            expectations = {
                reverse("portal:document_library_manage"),
                reverse("siteconfig:feature_control_panel"),
                reverse("studio_os:output"),
                reverse("siteconfig:console_domains_hub"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)

    def test_announcement_change_form_links_to_control_plane_surfaces(self):
        """P3: portal global Announcement banner → communication inbox + backend + hub."""
        ann = Announcement.objects.create(
            title="Admin UI smoke announcement",
            message="Smoke body for escape hatch test.",
        )
        model_admin = tenant_admin_site._registry[Announcement]
        path = reverse(
            "admin:portal_announcement_change",
            args=[ann.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(ann.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-announcement-cp-escape-heading", body)
            expectations = {
                reverse("communication:announcement_list_pending"),
                reverse("accounts:backend_dashboard"),
                reverse("siteconfig:console_domains_hub"),
            }
            for expect_path in expectations:
                self.assertIn(
                    expect_path,
                    body,
                    msg=f"missing control-plane link target {expect_path}",
                )
        finally:
            set_urlconf(None)
