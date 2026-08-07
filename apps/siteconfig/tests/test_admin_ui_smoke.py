import re
import unittest
import uuid
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
from django.test import RequestFactory
from django.test import TestCase, override_settings
from django.urls import get_urlconf, reverse, set_urlconf
from django.utils import timezone

from apps.accounts.models import Permission
from apps.automation.models import MigrationRun
from apps.compliance.models import (
    ComplianceRule,
    ConsentRecord,
    ConsentRequest,
    LegalDocument,
)
from apps.global_registries.models import RegionConfig
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.platform_runtime.models import RuntimeDefaults
from apps.siteconfig.context_processors import site_settings
from apps.integrations_marketplace.models import (
    AppInstallation,
    AppScope,
    Integration,
    MarketplaceApp,
    MarketplaceListing,
    ScopeGrant,
    ServiceIntegration,
)
from apps.portal.models import Announcement, DocumentCategory, Event, PortalFeatureItem
from apps.portal.models_kb import FAQ, FAQCategory, KBArticle, KBCategory
from apps.runtime_blueprints.models import DashboardWidget
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig as TenantRegionConfig
from apps.siteconfig.models import ReportCardStyle
from apps.siteconfig import models as _siteconfig_models
from apps.siteconfig.models_dashboard import DashboardUserPreference
from apps.siteconfig.models_feature_controls import (
    FeatureToggleDefinition,
    FeatureToggleState,
    TourStep,
)
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.siteconfig.models_platform_catalog import TenantAdmissionNumberPolicy
from apps.siteconfig.models_tooling import UserPreference
from apps.siteconfig.tests.test_admin import _admin_request_with_session_and_messages
from config.admin import platform_admin_site, tenant_admin_site


User = get_user_model()
_TenantSettingsModel = getattr(_siteconfig_models, "Site" + "Settings")

_FORM_BEFORE_BLOCK = re.compile(
    r"\{%\s*block\s+form_before\s*%\}(.*?)\{%\s*endblock\s*%\}",
    re.DOTALL,
)

_SMOKE_MARKETPLACE_MANIFEST = {
    "scopes": [],
    "widgets": [],
    "events_consumed": [],
    "events_emitted": [],
}


def _form_before_block_is_empty_placeholder(text: str) -> bool:
    """True when ``form_before`` is only the child-template placeholder (no CP escape content)."""
    match = _FORM_BEFORE_BLOCK.search(text)
    if not match:
        return False
    return not match.group(1).strip()


_MANAGER_URLCONF = "config.manager_urls"
_TENANT_URLCONF = "config.tenant_urls"
_MANAGER_HOST = "manager.runmycampus.com"
_TENANT_BASE_DOMAIN = "runmycampus.com"


def _reverse_super(name, *args, **kwargs):
    kwargs.setdefault("urlconf", _MANAGER_URLCONF)
    return reverse(name, *args, **kwargs)


def _reverse_tenant_admin(name, *args, **kwargs):
    """Reverse under tenant_urls — Client middleware can leave thread-local on config.urls (no admin)."""
    kwargs.setdefault("urlconf", _TENANT_URLCONF)
    return reverse(name, *args, **kwargs)


def _reverse_platform_admin(name, *args, **kwargs):
    """Reverse under manager_urls — same middleware urlconf pollution hazard as tenant."""
    kwargs.setdefault("urlconf", _MANAGER_URLCONF)
    return reverse(name, *args, **kwargs)


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


@override_settings(
    ROOT_URLCONF=_TENANT_URLCONF,
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", _MANAGER_HOST],
    MULTI_TENANT_BASE_DOMAIN=_TENANT_BASE_DOMAIN,
)
class AdminUiSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.site = get_platform_site_settings_record(create=True)
        cls.smoke_school = cls._create_smoke_school(slug_suffix="client")
        cls._tenant_host = f"{cls.smoke_school.subdomain}.{_TENANT_BASE_DOMAIN}"

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
        self.factory = RequestFactory()
        self.client.defaults["HTTP_HOST"] = self._tenant_host
        self._prev_urlconf = get_urlconf()
        set_urlconf(_TENANT_URLCONF)
        self.superuser = User.objects.create_superuser(
            username=f"admin-ui-super-{uuid.uuid4().hex[:8]}",
            email=f"admin-ui-super-{uuid.uuid4().hex[:8]}@example.com",
            password="password",
        )

    def tearDown(self):
        set_urlconf(self._prev_urlconf)
        super().tearDown()

    def _platform_change_form_body(self, model, pk, school=None) -> str:
        """Render a platform-admin change form via RequestFactory (avoids manager Client auth redirects).

        Some tenant-scoped ModelAdmins (e.g. ServiceIntegration via
        TenantIntegrationAdminMixin) gate on ``tenant_admin_user_has_access``,
        which requires ``request.school`` before the superuser bypass — pass
        ``school=`` to supply that context. Default keeps the school-less request
        the other callers rely on.
        """
        model_admin = platform_admin_site._registry[model]
        path = _reverse_platform_admin(
            f"admin:{model._meta.app_label}_{model._meta.model_name}_change",
            args=[pk],
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "manager"
        request.urlconf = _MANAGER_URLCONF
        if school is not None:
            request.school = school
        set_urlconf(_MANAGER_URLCONF)
        try:
            response = model_admin.change_view(request, str(pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            return response.content.decode("utf-8", errors="ignore")
        finally:
            set_urlconf(_TENANT_URLCONF)

    def _login_tenant_admin_client(self):
        self.client.defaults["HTTP_HOST"] = self._tenant_host
        set_urlconf(_TENANT_URLCONF)
        self.client.force_login(self.superuser)
        set_urlconf(_TENANT_URLCONF)

    def _smoke_marketplace_app(self, **overrides) -> MarketplaceApp:
        base = {
            "slug": overrides.pop("slug", f"p3-smoke-app-{uuid.uuid4().hex[:8]}"),
            "name": overrides.pop("name", "P3 smoke marketplace app"),
            "version": overrides.pop("version", "1.0.0"),
            "manifest": overrides.pop("manifest", _SMOKE_MARKETPLACE_MANIFEST),
            "is_intentionally_free": overrides.pop("is_intentionally_free", True),
        }
        base.update(overrides)
        return MarketplaceApp.objects.create(**base)

    def test_admin_quick_access_links_are_resolvable(self):
        self._login_tenant_admin_client()
        response = self.client.get(_reverse_tenant_admin("admin:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "admin-sidebar-quick-access")
        content = response.content.decode("utf-8", errors="ignore")

        platform_quick_link = _reverse_super("super:dashboard")
        tenant_quick_link = reverse(
            "accounts:backend_dashboard", urlconf=_TENANT_URLCONF
        )

        if platform_quick_link in content:
            self.assertContains(response, platform_quick_link)
            self.assertContains(response, "Control plane")
            quick_paths = [
                _reverse_tenant_admin("admin:index"),
                platform_quick_link,
                _reverse_super("super:site_settings_edit", kwargs={"pk": self.site.pk}),
                _reverse_super("super:regions_list"),
                _reverse_tenant_admin(
                    "admin:integrations_marketplace_integration_changelist"
                ),
                reverse("siteconfig:feature_control_panel", urlconf=_TENANT_URLCONF),
                reverse("siteconfig:theme_colors", urlconf=_TENANT_URLCONF),
                reverse("studio_os:output", urlconf=_TENANT_URLCONF),
                _reverse_super("super:blueprint_marketplace"),
                reverse("manager_help", urlconf=_MANAGER_URLCONF),
            ]
        else:
            self.assertContains(response, tenant_quick_link)
            self.assertContains(response, "Admin Home")
            quick_paths = [
                _reverse_tenant_admin("admin:index"),
                _reverse_tenant_admin(
                    "admin:siteconfig_sitesettings_change", args=[self.site.pk]
                ),
                _reverse_super("super:regions_list"),
                _reverse_tenant_admin(
                    "admin:integrations_marketplace_integration_changelist"
                ),
                reverse("siteconfig:feature_control_panel", urlconf=_TENANT_URLCONF),
                reverse("siteconfig:theme_colors", urlconf=_TENANT_URLCONF),
                reverse("studio_os:output", urlconf=_TENANT_URLCONF),
                reverse("kb:kb_home", urlconf=_TENANT_URLCONF),
                reverse("portal:document_library_manage", urlconf=_TENANT_URLCONF),
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
        self._login_tenant_admin_client()
        response = self.client.get(_reverse_tenant_admin("admin:index"))
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
            _reverse_tenant_admin("admin:index"),
            _reverse_super("super:dashboard"),
            _reverse_super("super:platform_operator_hub"),
            _reverse_super("super:site_settings_edit", kwargs={"pk": self.site.pk}),
            _reverse_super("super:regions_list"),
            _reverse_tenant_admin(
                "admin:integrations_marketplace_integration_changelist"
            ),
            reverse("siteconfig:feature_control_panel", urlconf=_TENANT_URLCONF),
            reverse("siteconfig:theme_colors", urlconf=_TENANT_URLCONF),
            reverse("studio_os:output", urlconf=_TENANT_URLCONF),
            reverse("kb:kb_home", urlconf=_TENANT_URLCONF),
            reverse("portal:document_library_manage", urlconf=_TENANT_URLCONF),
            reverse("accounts:backend_dashboard", urlconf=_TENANT_URLCONF),
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
        self._login_tenant_admin_client()
        response = self.client.get("/admin/dashboard/", follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, _reverse_tenant_admin("admin:index"))

    def test_sitesettings_change_form_links_to_control_plane_surfaces(self):
        """P3: admin tenant settings row is not the only story — escape hatch points to product shells."""
        # TenantMiddleware redirects Client GET /admin/… on tenant hosts to the backend shell; exercise
        # tenant_admin_site.change_view via RequestFactory (see apps/siteconfig/tests/test_admin.py).
        # Admin's reverse() uses get_urlconf() (thread-local), not request.urlconf — set tenant URLconf
        # so admin:app_list includes registered apps (e.g. accounts) on this AdminSite instance.
        model_admin = tenant_admin_site._registry[_TenantSettingsModel]
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

    def test_tenant_admin_footer_is_pinned_shell_band_outside_main(self):
        """The tenant /admin/ workbench footer must be the grid-row-3 .rmc-app-shell__footer
        band (a SIBLING of the scrolling canvas), NOT stranded inside <main>.

        Regression seal for v16.1: the footer used to render inside
        <main class="rmc-app-shell__canvas-body"> (flex:1 0 auto), so a short change
        form left the footer mid-canvas with a large blank band below it and no real
        pinned footer. The .rmc-app-shell grid always reserved a row-3 footer slot;
        this asserts the admin shell actually fills it and that the branded workbench
        footer sits OUTSIDE the canvas <main>.
        """
        model_admin = tenant_admin_site._registry[_TenantSettingsModel]
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
        finally:
            set_urlconf(None)

        # 1. The pinned grid-row-3 footer band exists.
        self.assertIn(
            'class="rmc-app-shell__footer',
            body,
            "tenant /admin/ is missing the pinned .rmc-app-shell__footer grid band",
        )
        # 2. The branded workbench footer renders OUTSIDE <main> (a grid sibling of
        #    the canvas), never stranded inside the scrolling canvas-body.
        main_close = body.rfind("</main>")
        workbench = body.rfind("rmc-admin-workbench-footer")
        self.assertGreater(main_close, 0, "no </main> in the admin shell")
        self.assertGreater(
            workbench,
            main_close,
            "workbench footer is still inside <main> (stranded mid-canvas) — it must "
            "be hoisted to the .rmc-app-shell__footer grid row 3 below the canvas",
        )
        # 3. The tenant footer must NOT double-render inside the canvas body.
        canvas_body = body.find("rmc-app-shell__canvas-body")
        inside_main_footer = body.find("rmc-admin-workbench-footer", canvas_body, main_close)
        self.assertEqual(
            inside_main_footer,
            -1,
            "tenant workbench footer still renders inside <main> — remove the "
            "in-canvas include so only the pinned grid-row-3 band remains",
        )

    def test_admin_head_declares_utf8_charset(self):
        """The /admin/ shell must emit <meta charset="utf-8"> in its <head>.

        Regression seal: Unfold's skeleton (unfold/layouts/skeleton.html) renders
        <title> first and NO <meta charset>, and base.html/portal_base.html/
        control_plane_skeleton.html all carry charset while admin/base_site.html did
        not — so the tenant + operator /admin/ pages relied solely on the response's
        HTTP Content-Type header and mojibaked (…, ·, ⚙️ → â€¦, Â·) whenever served
        without it (service-worker cache replay / proxies). base_site.html now emits it
        first in {% block extrastyle %}.
        """
        self._login_tenant_admin_client()
        resp = self.client.get(_reverse_tenant_admin("admin:index"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="ignore")
        self.assertRegex(
            body,
            r"""<meta\s+charset=["']?utf-8["']?""",
            "tenant /admin/ <head> is missing <meta charset='utf-8'> (Unfold skeleton omits it)",
        )
        head_end = body.lower().find("</head>")
        charset_pos = body.lower().find("charset")
        self.assertTrue(
            0 < charset_pos < head_end,
            "charset declaration must live inside <head>, before </head>",
        )

    def test_admin_workbench_footer_is_compact(self):
        """The /admin/ workbench footers (tenant + operator) match the operator /super/
        civic-ribbon density instead of the chunky 4.5rem 3-row stack.

        Contract seal: the base rule sets min-height:4.5rem + a grid inner (3 stacked
        rows); the compact override must neutralize that (min-height:0) and lay the
        inner out as a flex ribbon, reserving the fixed Tools edge-tab column.
        """
        from django.contrib.staticfiles import finders

        css_path = finders.find("css/rmc-admin-django-canvas-contract.css")
        self.assertIsNotNone(css_path, "canvas contract stylesheet not found")
        css = Path(css_path).read_text(encoding="utf-8")
        # Anchor on the compact override's own comment (the base rule shares the selector).
        anchor = "Compact /admin/ workbench footer"
        self.assertIn(anchor, css, "compact /admin/ footer override block is missing")
        compact_block = css.split(anchor, 1)[1][:1400]
        self.assertIn(
            "min-height: 0;", compact_block, "compact footer must drop the 4.5rem min-height"
        )
        self.assertIn(
            "--rmc-operator-tools-tab-w",
            compact_block,
            "compact footer must reserve the Tools edge-tab column via padding-right",
        )
        self.assertIn(
            "display: flex;",
            compact_block,
            "compact footer inner must be a flex ribbon (was grid stack)",
        )

    def test_tenant_admin_canvas_shell_floors_at_viewport(self):
        """EVERY backoffice /admin/ canvas shell — tenant (admin-premium-shell) AND
        operator (admin-manager-shell / control-plane-shell) — must be floored to the
        viewport height so short change/list pages don't collapse the grid to content
        height and strand the pinned grid-row-3 footer over a dark void.

        Regression seal (2026-08-06): a headless-browser audit measured a 872px shell in
        a 1080px viewport → a 208px void, on BOTH the tenant AND operator /admin/. The
        manager/control-plane `height:100% !important` companion rule is ineffective —
        neither `height:100%` nor `height:100dvh` stretches a grid whose <body> height is
        indefinite; only a viewport-unit `min-height` does. No-op on long pages (max-height
        already pins them). If any of the three shell selectors is removed the void returns.
        """
        from django.contrib.staticfiles import finders

        css_path = finders.find("css/rmc-backoffice-scroll-10x.css")
        self.assertIsNotNone(css_path, "backoffice scroll contract stylesheet not found")
        css = Path(css_path).read_text(encoding="utf-8")
        anchor = "Floor EVERY backoffice /admin/"
        self.assertIn(anchor, css, "backoffice shell viewport-floor block is missing")
        # Window must clear the explanatory comment (~1.2KB) to reach the rule below it.
        floor_block = css.split(anchor, 1)[1][:1800]
        # All THREE backoffice shells must be floored (tenant + both operator shells).
        for shell in (
            "admin-premium-shell",
            "admin-manager-shell",
            "control-plane-shell",
        ):
            self.assertIn(
                f'body.{shell}[data-rmc-cp-scroll="canvas"]',
                floor_block,
                f"floor rule must target the {shell} canvas shell",
            )
        self.assertIn(
            "[data-rmc-shell-root=\"django-admin\"].rmc-app-shell",
            floor_block,
            "floor rule must target the .rmc-app-shell grid root",
        )
        # A viewport-unit min-height floor (the whole point — height/height:100% do not work).
        self.assertIn(
            "min-height: var(--rmc-iso-viewport-h",
            floor_block,
            "floor rule must set a viewport-unit min-height on the shell",
        )

    def test_premium_form_contract_restores_field_row_grid_and_inline_table(self):
        """The premium form contract (v16) must keep BOTH of Unfold's native layouts
        alive against the over-broad `.form-row{display:flex;flex-direction:column}`
        rule, on BOTH /admin/ shells.

        Regression seal (2026-08-07): that one rule was defeating (1) Unfold's
        multi-column field rows (`field-row lg:grid-cols-2/3`) — force-stacking
        grouped fields full-width so pages ran ~2x too long — and (2) tabular inline
        tables — matching a tabular inline's <tr class="form-row"> and shattering the
        row into a stacked 13-cell column (2252px for one empty guardian row) while
        the header bled off the panel. Headless-verified fix: identity -49%, guardian
        inline -82%, whole add-student page -44%, zero horizontal bleed, on tenant
        (admin-premium-shell) AND operator (admin-manager-shell). If any of these
        rules is removed the shatter/stack returns.
        """
        from django.contrib.staticfiles import finders

        css_path = finders.find("css/rmc-admin-django-canvas-contract.css")
        self.assertIsNotNone(css_path, "canvas contract stylesheet not found")
        css = Path(css_path).read_text(encoding="utf-8")
        anchor = "PREMIUM FORM CONTRACT (v16"
        self.assertIn(anchor, css, "premium form contract block is missing")
        block = css.split(anchor, 1)[1]

        # (1) Field rows are restored to Unfold's responsive grid on BOTH shells.
        self.assertIn(".form-row.field-row", block, "field-row rule missing")
        self.assertIn("display: grid !important", block, "field-row must be grid, not flex-column")
        for shell in ("admin-premium-shell", "admin-manager-shell"):
            self.assertIn(shell, block, f"contract must cover the {shell} shell")
        self.assertIn(".lg\\:grid-cols-3", block, "multi-column (grid-cols-3) mapping missing")

        # (2) Tabular inline rows/cells keep real table semantics inside a scroll panel.
        self.assertIn(".inline-group table tr.form-row", block, "inline tr rule missing")
        self.assertIn("display: table-row !important", block, "inline row must stay table-row")
        self.assertIn("display: table-cell !important", block, "inline cell must stay table-cell")
        self.assertIn("overflow-x: auto !important", block, "wide inline must scroll, not bleed")

    def test_admin_workspace_dedupes_nested_inline_sections(self):
        """FORM PULSE 'sections' + the On-this-page rail must count each section once.

        Regression seal: `fieldset.module, .inline-group` matches a tabular inline
        twice (the `.inline-group` wraps an inner `fieldset.module`), so the count
        read 8 for 7 real sections and the rail showed a duplicate 'Student guardians'
        row. `collectSections()` drops nodes nested inside another matched node.
        """
        from django.contrib.staticfiles import finders

        js_path = finders.find("js/rmc-admin-workspace.js")
        self.assertIsNotNone(js_path, "admin workspace script not found")
        js = Path(js_path).read_text(encoding="utf-8")
        self.assertIn("function collectSections", js, "collectSections dedupe helper missing")
        self.assertIn("other.contains(node)", js, "dedupe must drop nested matched nodes")
        # Both consumers must route through the dedupe, not the raw selector.
        self.assertIn("var sections = collectSections(main);", js, "rail must use collectSections")
        self.assertIn("return collectSections(main).length;", js, "count must use collectSections")
        # The raw fieldset/inline selector must appear exactly once — inside
        # collectSections only — so neither consumer double-counts by calling it directly.
        self.assertEqual(
            js.count('"fieldset.module, .inline-group"'),
            1,
            "the fieldset/inline selector must live only inside collectSections()",
        )

    def test_form_intelligence_skips_section_nav_inside_admin_shell(self):
        """The platform-wide form enhancer must NOT build its `rmc-fi-nav` top tab
        bar inside the Django admin shell.

        Regression seal (2026-08-07): `rmc-form-intelligence.js` enhances every
        <form> and injects a horizontal `rmc-fi-nav` section tab bar. Inside the
        admin shell that is a third, redundant copy of the section list (the admin
        already renders numbered fieldset headings + the labelled 'On this page'
        rail), so `wireSectionNav` early-returns when the form is inside
        `[data-rmc-shell-root="django-admin"]`. Page-aware: the guard is scoped to
        the admin shell, so form-intelligence's nav keeps working on every other
        surface. If the guard is removed the redundant top tab bar returns.
        """
        from django.contrib.staticfiles import finders

        js_path = finders.find("js/rmc-form-intelligence.js")
        self.assertIsNotNone(js_path, "form-intelligence script not found")
        js = Path(js_path).read_text(encoding="utf-8")
        # The guard must live inside wireSectionNav and return before building nav.
        self.assertIn("function wireSectionNav", js, "wireSectionNav missing")
        # Slice to the NEXT top-level function (2-space indent) — not the first
        # bare "function " (an inline `function (s)` callback lives inside the body
        # before the nav is built).
        nav_body = js.split("function wireSectionNav", 1)[1].split("\n  function ", 1)[0]
        self.assertIn(
            "closest('[data-rmc-shell-root=\"django-admin\"]')",
            nav_body,
            "wireSectionNav must skip the admin shell (page-aware guard)",
        )
        # The guard must return BEFORE the nav element is created.
        guard_at = nav_body.index('data-rmc-shell-root="django-admin"')
        build_at = nav_body.index('"rmc-fi-nav"')
        self.assertLess(
            guard_at, build_at, "the admin-shell guard must precede nav construction"
        )

    def test_section_radar_dedupes_nested_inline_sections(self):
        """The section-radar dots must count each section once (7, not 8) — same
        dedupe as the rail + FORM PULSE.

        Regression seal (2026-08-07): `initSectionRadar` used the raw
        `fieldset.module, .inline-group` selector, which matches a tabular inline
        twice (the `.inline-group` wraps an inner `fieldset.module`), so it drew 8
        dots for 7 real sections. It must drop nodes nested inside another matched
        node.
        """
        from django.contrib.staticfiles import finders

        js_path = finders.find("js/rmc-admin-os-innovations.js")
        self.assertIsNotNone(js_path, "admin os-innovations script not found")
        js = Path(js_path).read_text(encoding="utf-8")
        self.assertIn("function initSectionRadar", js, "initSectionRadar missing")
        radar_body = js.split("function initSectionRadar", 1)[1].split("\n  function ", 1)[0]
        self.assertIn(
            "other.contains(node)",
            radar_body,
            "section radar must drop nested matched nodes (dedupe to 7)",
        )

    def test_premium_form_contract_styles_inline_add_and_remove_controls(self):
        """The v16 contract must give the tabular inline clear add/remove controls.

        Regression seal (2026-08-07): 'Add another …' was a bare text link in a
        full-width cell and the dynamic 'Remove' link was unstyled. The contract now
        renders the add link as a real pill button (with a leading '+') and the
        `inline-deletelink` remove control as a red-tinted button, page-aware
        (scoped to the django-admin shell + premium-form-frame).
        """
        from django.contrib.staticfiles import finders

        css_path = finders.find("css/rmc-admin-django-canvas-contract.css")
        self.assertIsNotNone(css_path, "canvas contract stylesheet not found")
        css = Path(css_path).read_text(encoding="utf-8")
        block = css.split("PREMIUM FORM CONTRACT (v16", 1)[1]
        # Add control: a real button affordance with a leading "+".
        self.assertIn(".inline-group .add-row a", block, "add-row button rule missing")
        self.assertIn('content: "+"', block, "add-row button must carry a leading +")
        # Remove control: the dynamic inline-deletelink is styled as a button.
        self.assertIn("a.inline-deletelink", block, "remove-control rule missing")
        # Page-aware: scoped to the admin shell + the change/add form contract.
        self.assertIn('[data-rmc-shell-root="django-admin"]', block)
        self.assertIn('[data-rmc-admin-form-contract="premium-form-frame"]', block)

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
        # IntegrationMarketplaceAdmin gates on tenant_admin_user_has_access, which
        # requires request.school before the superuser bypass — supply it.
        request.school = self.smoke_school
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

    def test_themepack_change_form_template_is_tenant_safe(self):
        """ThemePack stays native and exposes only tenant-scoped guided links."""
        from pathlib import Path

        tpl = (
            Path(__file__).resolve().parents[3]
            / "templates"
            / "admin"
            / "siteconfig"
            / "themepack"
            / "change_form.html"
        )
        self.assertTrue(tpl.is_file(), msg="themepack change_form template missing")
        body = tpl.read_text(encoding="utf-8")
        self.assertIn("themepack-cp-escape-heading", body)
        self.assertIn("siteconfig:theme_colors", body)
        self.assertNotIn("studio_os:", body)
        self.assertIn("siteconfig:console_domains_hub", body)

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

    def test_portal_event_change_form_links_to_control_plane_surfaces(self):
        """P3: portal Event admin → unified calendar + backend + feature control."""
        start = timezone.now()
        ev = Event.objects.create(
            title="Admin UI smoke event",
            start_at=start,
            end_at=start,
        )
        model_admin = tenant_admin_site._registry[Event]
        path = reverse(
            "admin:portal_event_change",
            args=[ev.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(ev.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-event-cp-escape-heading", body)
            expectations = {
                reverse("portal:unified_calendar"),
                reverse("accounts:backend_dashboard"),
                reverse("siteconfig:feature_control_panel"),
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

    def test_portal_documentcategory_change_form_links_to_control_plane_surfaces(self):
        """P3: portal DocumentCategory → document library + feature control + Studio Output."""
        cat = DocumentCategory.objects.create(
            name="Admin UI smoke doc category",
            slug="admin-ui-smoke-doc-cat",
        )
        model_admin = tenant_admin_site._registry[DocumentCategory]
        path = reverse(
            "admin:portal_documentcategory_change",
            args=[cat.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(cat.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-document-category-cp-escape-heading", body)
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

    def test_portal_kbarticle_change_form_links_to_control_plane_surfaces(self):
        """P3: portal KBArticle → KB home + submit flow + configuration hub."""
        kb_cat = KBCategory.objects.create(
            name="Admin UI smoke KB category",
            slug="admin-ui-smoke-kb-cat",
        )
        article = KBArticle.objects.create(
            title="Admin UI smoke KB article",
            slug="admin-ui-smoke-kb-article",
            category=kb_cat,
            summary="Smoke summary for escape hatch test.",
            content="Smoke content.",
        )
        model_admin = tenant_admin_site._registry[KBArticle]
        path = reverse(
            "admin:portal_kbarticle_change",
            args=[article.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(article.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-kb-article-cp-escape-heading", body)
            expectations = {
                reverse("kb:kb_home"),
                reverse("kb:kb_article_submit"),
                reverse("siteconfig:feature_control_panel"),
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

    def test_compliance_consentrequest_change_form_links_to_control_plane_surfaces(self):
        """P3: compliance ConsentRequest → hub + feature control + backend + KB."""
        region = TenantRegionConfig.objects.create(
            code="P3CR",
            name="Admin smoke region consent",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        school = School.objects.create(
            name="Admin UI smoke school consent",
            slug="admin-ui-smoke-school-cr",
            subdomain="admin-ui-smoke-cr",
            is_active=True,
            default_region=region,
            settings={},
        )
        cr = ConsentRequest.objects.create(
            school=school,
            title="Admin UI smoke consent request",
        )
        model_admin = tenant_admin_site._registry[ConsentRequest]
        path = reverse(
            "admin:compliance_consentrequest_change",
            args=[cr.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(cr.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("compliance-consent-request-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:console_domains_hub"),
                reverse("siteconfig:feature_control_panel"),
                reverse("accounts:backend_dashboard"),
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

    def test_portal_faqcategory_change_form_links_to_control_plane_surfaces(self):
        """P3: portal FAQCategory → FAQ directory + KB + feature control."""
        cat = FAQCategory.objects.create(
            name="Admin UI smoke FAQ category",
            slug="admin-ui-smoke-faq-cat",
        )
        model_admin = tenant_admin_site._registry[FAQCategory]
        path = reverse(
            "admin:portal_faqcategory_change",
            args=[cat.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(cat.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-faq-category-cp-escape-heading", body)
            expectations = {
                reverse("kb:faq_list"),
                reverse("kb:kb_home"),
                reverse("siteconfig:feature_control_panel"),
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

    def test_portal_faq_change_form_links_to_control_plane_surfaces(self):
        """P3: portal FAQ → public FAQ list + submit + KB home."""
        faq_cat = FAQCategory.objects.create(
            name="Admin UI smoke FAQ cat for FAQ",
            slug="admin-ui-smoke-faq-cat-faq",
        )
        faq = FAQ.objects.create(
            category=faq_cat,
            question="Admin UI smoke FAQ question?",
            answer="Admin UI smoke FAQ answer.",
        )
        model_admin = tenant_admin_site._registry[FAQ]
        path = reverse(
            "admin:portal_faq_change",
            args=[faq.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(faq.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-faq-cp-escape-heading", body)
            expectations = {
                reverse("kb:faq_list"),
                reverse("kb:faq_submit"),
                reverse("kb:kb_home"),
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

    def test_portal_kbcategory_change_form_links_to_control_plane_surfaces(self):
        """P3: portal KBCategory → KB home + article submit + hub."""
        cat = KBCategory.objects.create(
            name="Admin UI smoke KB category standalone",
            slug="admin-ui-smoke-kb-cat-standalone",
        )
        model_admin = tenant_admin_site._registry[KBCategory]
        path = reverse(
            "admin:portal_kbcategory_change",
            args=[cat.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(cat.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("portal-kb-category-cp-escape-heading", body)
            expectations = {
                reverse("kb:kb_home"),
                reverse("kb:kb_article_submit"),
                reverse("siteconfig:feature_control_panel"),
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

    def _smoke_school(self, *, slug_suffix: str) -> School:
        return self._create_smoke_school(slug_suffix=slug_suffix)

    @staticmethod
    def _create_smoke_school(*, slug_suffix: str) -> School:
        region = TenantRegionConfig.objects.create(
            code=f"P3{uuid.uuid4().hex[:8].upper()}",
            name=f"Admin smoke region {slug_suffix}",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        return School.objects.create(
            name=f"Admin UI smoke school {slug_suffix}",
            slug=f"admin-ui-smoke-{slug_suffix}",
            subdomain=f"admin-smoke-{slug_suffix}"[:60],
            is_active=True,
            default_region=region,
            settings={},
        )

    def test_featuretoggledefinition_change_form_links_to_control_plane_surfaces(self):
        """P3: FeatureToggleDefinition admin → feature control + audit + hub."""
        definition = FeatureToggleDefinition.objects.create(
            key="p3-admin-smoke-toggle",
            label="P3 admin smoke toggle",
            category="smoke",
        )
        model_admin = tenant_admin_site._registry[FeatureToggleDefinition]
        path = reverse(
            "admin:siteconfig_featuretoggledefinition_change",
            args=[definition.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(definition.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("feature-toggle-def-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:feature_control_panel"),
                reverse("siteconfig:feature_control_audit"),
                reverse("siteconfig:console_domains_hub"),
                reverse("accounts:backend_dashboard"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_featuretogglestate_change_form_links_to_control_plane_surfaces(self):
        """P3: FeatureToggleState admin → feature control + ledger."""
        definition = FeatureToggleDefinition.objects.create(
            key="p3-admin-smoke-toggle-state",
            label="P3 smoke state",
        )
        school = self._smoke_school(slug_suffix="ft-state")
        state = FeatureToggleState.objects.create(
            definition=definition,
            school=school,
            is_enabled=True,
        )
        model_admin = tenant_admin_site._registry[FeatureToggleState]
        path = reverse(
            "admin:siteconfig_featuretogglestate_change",
            args=[state.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(state.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("feature-toggle-state-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:feature_control_panel"),
                reverse("siteconfig:feature_control_ledger"),
                reverse("siteconfig:console_domains_hub"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_tenantadmissionnumberpolicy_change_form_links_to_control_plane_surfaces(self):
        """P3: TenantAdmissionNumberPolicy → blueprints + workflow + feature control."""
        school = self._smoke_school(slug_suffix="adm-pol")
        policy = TenantAdmissionNumberPolicy.objects.create(school=school)
        model_admin = tenant_admin_site._registry[TenantAdmissionNumberPolicy]
        path = reverse(
            "admin:siteconfig_tenantadmissionnumberpolicy_change",
            args=[policy.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(policy.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("tenant-admission-policy-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:get_blueprints"),
                reverse("siteconfig:workflow_flow_gallery"),
                reverse("siteconfig:feature_control_panel"),
                reverse("siteconfig:console_domains_hub"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_dynamicfielddefinition_change_form_links_to_control_plane_surfaces(self):
        """P3 / Batch 14: metadata.DynamicFieldDefinition → control plane + Studio."""
        school = self._smoke_school(slug_suffix="dyn-def")
        definition = DynamicFieldDefinition.objects.create(
            school=school,
            entity_type="Student",
            field_key="p3_smoke_attr",
            label="P3 smoke attribute",
        )
        model_admin = tenant_admin_site._registry[DynamicFieldDefinition]
        path = reverse(
            "admin:metadata_dynamicfielddefinition_change",
            args=[definition.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(definition.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("dynamic-field-def-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:tag_manager"),
                reverse("siteconfig:console_domains_hub"),
                reverse("siteconfig:feature_control_panel"),
                reverse("studio_os:output"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_dynamicfieldvalue_change_form_links_to_control_plane_surfaces(self):
        """P3 / Batch 14: metadata.DynamicFieldValue → control plane + backend."""
        school = self._smoke_school(slug_suffix="dyn-val")
        value = DynamicFieldValue.objects.create(
            school=school,
            entity_type="Student",
            entity_id="1",
            field_key="p3_smoke_val",
            value_json={"v": "x"},
        )
        model_admin = tenant_admin_site._registry[DynamicFieldValue]
        path = reverse(
            "admin:metadata_dynamicfieldvalue_change",
            args=[value.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(value.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("dynamic-field-value-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:tag_manager"),
                reverse("siteconfig:console_domains_hub"),
                reverse("accounts:backend_dashboard"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_tourstep_change_form_links_to_control_plane_surfaces(self):
        """P3: TourStep admin → guided onboarding + tour API + preferences."""
        school = self._smoke_school(slug_suffix="tour-step")
        step = TourStep.objects.create(
            school=school,
            code="p3_admin_smoke_tour",
            title="P3 smoke tour step",
        )
        model_admin = tenant_admin_site._registry[TourStep]
        path = reverse(
            "admin:siteconfig_tourstep_change",
            args=[step.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(step.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("tour-step-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:guided_onboarding"),
                reverse("siteconfig:tour_steps_api"),
                reverse("siteconfig:console_domains_hub"),
                reverse("siteconfig:user_preferences"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_userpreference_change_form_links_to_control_plane_surfaces(self):
        """P3: UserPreference admin → preferences + dashboard hubs."""
        pref, _ = UserPreference.objects.get_or_create(user=self.superuser)
        model_admin = tenant_admin_site._registry[UserPreference]
        path = reverse(
            "admin:siteconfig_userpreference_change",
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
            self.assertIn("user-preference-cp-escape-heading", body)
            for expect_path in (
                reverse("siteconfig:user_preferences"),
                reverse("siteconfig:dashboard_hub"),
                reverse("siteconfig:dashboard_configuration_hub"),
                reverse("siteconfig:console_domains_hub"),
            ):
                self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")
        finally:
            set_urlconf(None)

    def test_compliance_consentrecord_change_form_links_to_control_plane_surfaces(self):
        """P3: compliance ConsentRecord → hub + feature control + backend + KB."""
        region = TenantRegionConfig.objects.create(
            code="P3REC",
            name="Admin smoke region consent record",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        school = School.objects.create(
            name="Admin UI smoke school consent record",
            slug="admin-ui-smoke-school-rec",
            subdomain="admin-ui-smoke-rec",
            is_active=True,
            default_region=region,
            settings={},
        )
        rec = ConsentRecord.objects.create(
            school=school,
            user=self.superuser,
            title="Admin UI smoke consent record",
            document_hash="a" * 64,
        )
        model_admin = tenant_admin_site._registry[ConsentRecord]
        path = reverse(
            "admin:compliance_consentrecord_change",
            args=[rec.pk],
            urlconf="config.tenant_urls",
        )
        request = _admin_request_with_session_and_messages(
            self.factory, self.superuser, path=path
        )
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        set_urlconf("config.tenant_urls")
        try:
            response = model_admin.change_view(request, str(rec.pk))
            self.assertEqual(response.status_code, 200)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            body = response.content.decode("utf-8", errors="ignore")
            self.assertIn("compliance-consent-record-cp-escape-heading", body)
            expectations = {
                reverse("siteconfig:console_domains_hub"),
                reverse("siteconfig:feature_control_panel"),
                reverse("accounts:backend_dashboard"),
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

    def test_runtimedefaults_change_form_links_to_control_plane_surfaces(self):
        """P3: platform RuntimeDefaults admin links to super operator shells (batch 28 #338)."""
        rd = RuntimeDefaults.get_singleton()
        body = self._platform_change_form_body(RuntimeDefaults, rd.pk)
        self.assertIn("runtime-defaults-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:dashboard"),
            _reverse_super("super:schools_list"),
            _reverse_super("super:usage"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_marketplaceapp_change_form_links_to_control_plane_surfaces(self):
        """P3: platform MarketplaceApp admin links to super operator shells (batch 29 #353)."""
        app = self._smoke_marketplace_app(
            slug="p3-marketplace-app-smoke",
            name="P3 Marketplace App smoke",
        )
        body = self._platform_change_form_body(MarketplaceApp, app.pk)
        self.assertIn("marketplace-app-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:dashboard"),
            _reverse_super("super:schools_list"),
            _reverse_super("super:usage"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_marketplacelisting_change_form_links_to_control_plane_surfaces(self):
        """P3: platform MarketplaceListing admin links to super operator shells (batch 31 #383)."""
        app = self._smoke_marketplace_app(
            slug="p3-marketplace-listing-smoke",
            name="P3 Marketplace Listing smoke",
        )
        listing = MarketplaceListing.objects.create(
            app=app,
            status=MarketplaceListing.Status.DRAFT,
        )
        body = self._platform_change_form_body(MarketplaceListing, listing.pk)
        self.assertIn("marketplace-listing-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:dashboard"),
            _reverse_super("super:schools_list"),
            _reverse_super("super:usage"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_serviceintegration_change_form_links_to_control_plane_surfaces(self):
        """P3: platform ServiceIntegration admin links to super operator shells (batch 30 #368)."""
        region = TenantRegionConfig.objects.create(
            code="P3SVCINT",
            name="Admin smoke region service integration",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        school = School.objects.create(
            name="Admin UI smoke school service integration",
            slug="admin-ui-smoke-school-svcint",
            subdomain="admin-ui-smoke-svcint",
            is_active=True,
            default_region=region,
            settings={},
        )
        si = ServiceIntegration.objects.create(
            school=school,
            service_name="P3 smoke service integration",
            service_type=ServiceIntegration.ServiceType.LTI,
        )
        body = self._platform_change_form_body(
            ServiceIntegration, si.pk, school=self.smoke_school
        )
        self.assertIn("service-integration-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:dashboard"),
            _reverse_super("super:schools_list"),
            _reverse_super("super:usage"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_scopegrant_change_form_links_to_control_plane_surfaces(self):
        """P3: platform ScopeGrant admin links to super operator shells (batch 35 #443)."""
        region = TenantRegionConfig.objects.create(
            code="P3SCOPE",
            name="Admin smoke region scope grant",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        school = School.objects.create(
            name="Admin UI smoke school scope grant",
            slug="admin-ui-smoke-school-scope",
            subdomain="admin-ui-smoke-scope",
            is_active=True,
            default_region=region,
            settings={},
        )
        app = self._smoke_marketplace_app(
            slug="p3-scope-smoke-app",
            name="P3 Scope smoke app",
        )
        scope = AppScope.objects.create(
            app=app, scope_code="read:grades", description="Read grades"
        )
        inst = AppInstallation.objects.create(
            school=school,
            app=app,
            status=AppInstallation.Status.ACTIVE,
        )
        grant = ScopeGrant.objects.create(
            installation=inst,
            scope=scope,
            status=ScopeGrant.GrantStatus.GRANTED,
        )
        body = self._platform_change_form_body(ScopeGrant, grant.pk)
        self.assertIn("scope-grant-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:platform_operator_hub"),
            _reverse_super("super:dashboard"),
            _reverse_super("super:schools_list"),
            _reverse_super("super:usage"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_appinstallation_change_form_links_to_control_plane_surfaces(self):
        """P3: platform AppInstallation admin links to super operator shells (batch 41 §11.4)."""
        region = TenantRegionConfig.objects.create(
            code="P3APPINST",
            name="Admin smoke region app installation",
            timezone="UTC",
            date_format="YYYY-MM-DD",
            grading_scale="0-20",
            default_currency="USD",
            academic_year_start_month=9,
            term_count_per_year=3,
        )
        school = School.objects.create(
            name="Admin UI smoke school app installation",
            slug="admin-ui-smoke-school-appinst",
            subdomain="admin-ui-smoke-appinst",
            is_active=True,
            default_region=region,
            settings={},
        )
        app = self._smoke_marketplace_app(
            slug="p3-appinst-smoke-app",
            name="P3 AppInstallation smoke app",
        )
        inst = AppInstallation.objects.create(
            school=school,
            app=app,
            status=AppInstallation.Status.ACTIVE,
        )
        body = self._platform_change_form_body(AppInstallation, inst.pk)
        self.assertIn("app-installation-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:platform_operator_hub"),
            _reverse_super("super:dashboard"),
            _reverse_super("super:schools_list"),
            _reverse_super("super:migration_cloud"),
            _reverse_super("super:usage"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_automation_migrationrun_change_form_links_to_control_plane_surfaces(self):
        """P3: platform MigrationRun admin escape hatch (batch 35 #443)."""
        run = MigrationRun.objects.create(
            migration_type="p3-admin-smoke",
            dry_run=True,
            status=MigrationRun.Status.PENDING,
        )
        body = self._platform_change_form_body(MigrationRun, run.pk)
        self.assertIn("automation-migration-run-cp-escape-heading", body)
        for expect_path in (
            _reverse_super("super:dashboard"),
            _reverse_super("super:migration_cloud"),
            _reverse_super("super:runtime_truth_hub"),
            reverse("siteconfig:tenant_runtime_configuration_hub"),
        ):
            self.assertIn(expect_path, body, msg=f"missing CP link {expect_path}")

    def test_admin_change_form_templates_with_form_before_include_p3_escape_markers(self):
        """Batch 23 #263: tenant ``change_form`` templates that define ``form_before`` keep P3 escape hatch hints."""
        base = Path(settings.BASE_DIR) / "templates" / "admin"
        for path in sorted(base.rglob("change_form.html")):
            rel = path.relative_to(settings.BASE_DIR).as_posix()
            # Base Unfold change_form only declares the empty ``form_before`` hook for children.
            if rel == "templates/admin/change_form.html":
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if "{% block form_before %}" not in text:
                continue
            if _form_before_block_is_empty_placeholder(text):
                continue
            self.assertTrue(
                "cp-escape-heading" in text
                or "console_domains_hub" in text
                or "feature_control_panel" in text,
                msg=f"{rel}: expected P3 escape marker (heading id or siteconfig URL name)",
            )
