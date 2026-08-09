"""
Assert marketing base template does not load app-only stylesheets.
Marketing surface must use only marketing shell and assets (no dashboard-*, design-system-unified, theme-everywhere-dark).
"""

import unittest
from pathlib import Path


# App-only CSS that must NOT appear in marketing base
FORBIDDEN_IN_MARKETING = (
    "design-system-unified.css",
    "dashboard-responsive.css",
    "dashboard-high-contrast.css",
    "dashboard-text-visibility.css",
    "theme-everywhere-dark.css",
)


class MarketingShellTests(unittest.TestCase):
    """Marketing shell must not include app chrome CSS."""

    def test_base_marketing_does_not_load_app_only_css(self):
        """base_marketing.html must not reference design-system-unified, dashboard-*, or theme-everywhere-dark."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "marketing" / "base_marketing.html"
        if not template.is_file():
            self.skipTest("templates/marketing/base_marketing.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        for forbidden in FORBIDDEN_IN_MARKETING:
            self.assertNotIn(
                forbidden,
                text,
                f"Marketing base must not load app-only CSS: {forbidden}",
            )

    def test_marketing_base_schools_does_not_load_app_only_css(self):
        """schools/marketing_base.html extends base_marketing; ensure it doesn't add app-only CSS."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "schools" / "marketing_base.html"
        if not template.is_file():
            self.skipTest("templates/schools/marketing_base.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        for forbidden in FORBIDDEN_IN_MARKETING:
            self.assertNotIn(
                forbidden,
                text,
                f"Marketing base (schools) must not load app-only CSS: {forbidden}",
            )


class PortalBaseTenantShellTests(unittest.TestCase):
    """Portal/backend/Studio tenant shell must not load control-plane or marketing-only CSS."""

    def test_portal_base_keeps_tenant_surface_contract(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "portal_base.html"
        if not template.is_file():
            self.skipTest("templates/portal_base.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        # data-surface is now host-conditional: control-plane on the manager host,
        # tenant everywhere else (the default portal surface).
        self.assertIn("control-plane{% else %}tenant", text)
        for required in (
            "css/design-system-unified.css",
            "css/platform-responsive-touch.css",
        ):
            self.assertIn(
                required,
                text,
                f"portal_base must load tenant app chrome: {required}",
            )
        for forbidden in (
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ):
            self.assertNotIn(
                forbidden,
                text,
                f"portal_base must not load other-surface shell CSS: {forbidden}",
            )


class ShellSurfaceFamilyContractTests(unittest.TestCase):
    """Shell/control-plane convergence (batches 986–988): shared data-* contract for audits and tooling."""

    def test_portal_base_exposes_authenticated_shell_contract(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "portal_base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("data-rmc-shell-root=", text)
        self.assertIn("rmc_shell.portal_shell_root", text)
        self.assertIn("rmc_shell.portal_default_document_title", text)
        self.assertIn("partials/shell_rmc_registry_html_attrs.html", text)
        self.assertIn("partials/shell_portal_layout_wrap_open.html", text)
        wrap = (root / "templates" / "partials" / "shell_portal_layout_wrap_open.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("data-rmc-authenticated-shell=", wrap)
        self.assertIn("portal_wrap_authenticated_shell", wrap)
        self.assertIn('data-shell-sidebar="portal"', text)
        self.assertIn('data-shell-sidebar-mount="desktop"', text)
        self.assertIn('data-shell-sidebar-mount="offcanvas"', text)
        self.assertIn('data-shell-main="portal"', text)
        partial = (root / "templates" / "partials" / "shell_rmc_registry_html_attrs.html").read_text(
            encoding="utf-8", errors="replace"
        )
        for needle in (
            "data-rmc-route-family=",
            "data-rmc-layout-token=",
            "data-rmc-nav-family=",
            "data-rmc-host-kind=",
            "data-rmc-main-region=",
        ):
            self.assertIn(needle, partial, f"registry partial must expose {needle!r} for html root")

    def test_shell_chrome_shared_partials_and_includes(self):
        """1005: django-messages, marketplace ops strip, breadcrumb row markers."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        dm = (root / "templates" / "partials" / "shell_chrome_django_messages.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('data-shell-chrome="django-messages"', dm)
        mk = (root / "templates" / "partials" / "shell_chrome_marketplace_tenant_ops_strip.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("data-shell-marketplace-ops=", mk)
        self.assertIn("data-shell-chrome=", mk)
        be = (root / "templates" / "partials" / "shell_chrome_backend_ops_strip.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("data-backend-ops-surface=", be)
        self.assertIn("data-backend-ops-links=", be)
        bsys = (root / "templates" / "partials" / "shell_chrome_backend_system_indicators.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("data-backend-system-indicators=", bsys)
        self.assertIn("data-backend-indicator=", bsys)
        bop = (root / "templates" / "partials" / "shell_chrome_backend_operational_status_load.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("backend-operational-status-load", bop)
        self.assertIn("backend-status-fragment", bop)
        tp = (root / "templates" / "partials" / "shell_chrome_django_messages_tenant_portal.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_messages_variant", tp)
        self.assertIn("shell_chrome_messages_include_announcement", tp)
        cpw = (root / "templates" / "partials" / "shell_chrome_django_messages_control_plane.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("control-plane", cpw)
        pb = (root / "templates" / "portal_base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("shell_chrome_django_messages_tenant_portal", pb)
        self.assertIn("shell_chrome_django_messages", pb)
        self.assertIn("shell_chrome_breadcrumb_row_open.html", pb)
        self.assertIn("shell_chrome_breadcrumb_row_between_primary_and_actions.html", pb)
        self.assertIn("shell_chrome_breadcrumb_row_close.html", pb)
        cp = (root / "templates" / "control_plane_base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("shell_chrome_django_messages_control_plane", cp)
        self.assertIn("shell_chrome_django_messages", cp)
        base = (root / "templates" / "base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("shell_chrome_django_messages_base_bootstrap", base)
        bsb = (root / "templates" / "partials" / "shell_chrome_django_messages_base_bootstrap.html").read_text(
            encoding="utf-8", errors="replace"
        )
        # 1046: shared chrome — base layout chains django-messages through the bootstrap wrapper
        # (variant base-bootstrap) instead of inlining a raw messages loop in base.html.
        self.assertIn("shell_chrome_django_messages.html", bsb)
        self.assertIn("base-bootstrap", bsb)
        self.assertIn("shell_chrome_breadcrumb_row_open.html", cp)
        self.assertIn("shell_chrome_breadcrumb_row_between_primary_and_actions.html", cp)
        self.assertIn("shell_chrome_breadcrumb_row_close.html", cp)
        self.assertIn("data-rmc-layout-token", cp)
        bd = (root / "templates" / "accounts" / "backend_dashboard.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_backend_ops_strip", bd)
        self.assertIn("shell_chrome_backend_system_indicators", bd)
        self.assertIn("shell_chrome_backend_operational_status_load", bd)
        self.assertIn("shell_chrome_breadcrumb_row_open.html", bd)
        self.assertIn("shell_chrome_backend_ops_depth_summary", bd)
        self.assertIn("shell_chrome_backend_ops_audit_snapshot", bd)
        self.assertIn("shell_chrome_backend_stats_core_strip", bd)
        self.assertIn("shell_chrome_backend_finance_pulse_strip", bd)
        self.assertIn("shell_chrome_backend_planner_recommended_next_strip", bd)
        prn = (
            root / "templates" / "partials" / "shell_chrome_backend_planner_recommended_next_strip.html"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("data-shell-chrome=\"backend-planner-recommended-next\"", prn)
        self.assertIn("planner-recommended-next", prn)
        kpi = (root / "templates" / "partials" / "shell_chrome_backend_stats_core_strip.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("backend-stats-core-strip", kpi)
        self.assertIn("core-kpi-counts", kpi)
        audit = (root / "templates" / "partials" / "shell_chrome_backend_ops_audit_snapshot.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("backend-audit-snapshot", audit)
        self.assertIn("audit-system-counts", audit)
        fin = (root / "templates" / "partials" / "shell_chrome_backend_finance_pulse_strip.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("backend-finance-pulse-strip", fin)
        self.assertIn("finance-pulse-counts", fin)
        cbanner = (root / "templates" / "partials" / "shell_chrome_contextual_info_banner.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("contextual-info-banner", cbanner)
        ph = (root / "templates" / "partials" / "shell_chrome_page_heading_actions_strip.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("page-heading-actions-strip", ph)
        self.assertIn("page-heading-actions-toolbar", ph)
        up = (root / "templates" / "siteconfig" / "user_preferences.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_contextual_info_banner.html", up)
        bl = (root / "templates" / "siteconfig" / "bulk_letters.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_page_heading_actions_strip.html", bl)
        st = (root / "templates" / "siteconfig" / "school_theme_settings.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_contextual_info_banner.html", st)
        self.assertIn("shell_chrome_page_heading_actions_strip.html", st)
        tac = (root / "templates" / "marketplace" / "tenant_app_catalog.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_marketplace_tenant_ops_strip", tac)

    def test_breadcrumb_actions_block_between_chrome_partials(self):
        """1012: Child templates must still override {% block breadcrumb_actions %} (order vs partials)."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        pb = (root / "templates" / "portal_base.html").read_text(encoding="utf-8", errors="replace")
        cp = (root / "templates" / "control_plane_base.html").read_text(encoding="utf-8", errors="replace")
        marker_block = "{% block breadcrumb_actions %}"
        for label, text in (("portal_base", pb), ("control_plane_base", cp)):
            between = text.find("shell_chrome_breadcrumb_row_between_primary_and_actions")
            block = text.find(marker_block)
            close = text.find("shell_chrome_breadcrumb_row_close")
            self.assertNotEqual(between, -1, label)
            self.assertNotEqual(block, -1, label)
            self.assertNotEqual(close, -1, label)
            self.assertLess(between, block, label)
            self.assertLess(block, close, label)
        child = (root / "templates" / "schools" / "super_workflow_packs.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn(marker_block, child)
        self.assertIn("js-return-to-origin", child)

    def test_base_html_includes_rmc_registry_partial(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("partials/shell_rmc_registry_html_attrs.html", text)

    def test_portal_sidebar_nav_shell_family(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "partials" / "portal_sidebar.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('data-shell-nav-family="portal"', text)

    def test_portal_and_control_plane_include_shared_session_chrome_partials(self):
        """1025: Preview + impersonation partials wired without breaking template blocks."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        pb = (root / "templates" / "portal_base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("shell_chrome_site_preview_banner_top.html", pb)
        self.assertIn("shell_chrome_impersonation_session_strip.html", pb)
        cp = (root / "templates" / "control_plane_base.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("shell_chrome_impersonation_session_strip.html", cp)

    def test_control_plane_base_and_sidebar_shell_contract(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        base = (root / "templates" / "control_plane_base.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("data-rmc-authenticated-shell=", base)
        self.assertIn("cp_layout_authenticated_shell", base)
        self.assertIn("data-rmc-layout-token=", base)
        self.assertIn("rmc_shell.layout_token", base)
        self.assertIn("rmc_shell.control_plane_product_title", base)
        self.assertIn("data-rmc-shell-title=", base)
        self.assertIn("rmc_shell.shell_sidebar_control_plane", base)
        self.assertIn('data-shell-sidebar="', base)
        self.assertIn("shell_chrome_breadcrumb_row_open.html", base)
        self.assertIn("shell_chrome_breadcrumb_row_between_primary_and_actions.html", base)
        self.assertIn("shell_chrome_breadcrumb_row_close.html", base)
        self.assertIn("{% block breadcrumbs %}", base)
        self.assertIn("{% block breadcrumb_actions %}", base)
        side = (root / "templates" / "partials" / "control_plane_sidebar.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('data-shell-nav-family="control-plane"', side)

    def test_studio_os_shell_tenant_and_control_plane_hosts(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        sh = (root / "templates" / "studio_os" / "shell.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("rmc_shell.layout_token", sh)
        self.assertIn("rmc_shell.shell_data_studio_host", sh)
        self.assertIn("data-rmc-nav-family=", sh)
        self.assertIn("rmc_shell.studio_os_sidebar_token", sh)
        self.assertIn("data-shell-sidebar=", sh)
        scp = (root / "templates" / "studio_os" / "shell_control_plane.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("rmc_shell.layout_token", scp)
        self.assertIn("rmc_shell.shell_data_studio_host", scp)
        self.assertIn("data-rmc-nav-family=", scp)

    def test_admin_base_site_sets_data_shell_layout(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "admin" / "base_site.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn("setAttribute('data-shell-layout', 'admin')", text)
        for needle in (
            "data-rmc-admin-shell",
            "data-rmc-shell-root",
            "setAttribute('data-rmc-route-family'",
            "rmc_shell.route_family",
        ):
            self.assertIn(needle, text, f"admin base_site should bridge RMC shell contract: {needle!r}")


class ShellWaveBatch989PlusContractTests(unittest.TestCase):
    """989+ — skeleton, Studio embed, siteconfig Phase B surface, role home, admin bridge, marketplace."""

    def test_control_plane_skeleton_root_and_body(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "control_plane_skeleton.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-rmc-shell-root="control-plane-skeleton"', text)
        self.assertIn("partials/shell_rmc_registry_html_attrs.html", text)
        self.assertIn("partials/shell_skip_link.html", text)
        self.assertIn('data-rmc-shell-body="control-plane-skeleton"', text)

    def test_shell_main_content_embed_attributes(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "studio_os" / "partials" / "shell_main_content.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn("data-shell-studio-region", text)
        self.assertIn("data-rmc-studio-os-embed", text)

    def test_tenant_runtime_hub_phase_b_surface(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        shell = root / "templates" / "siteconfig" / "tenant_runtime_configuration_hub.html"
        text = shell.read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-siteconfig-surface="tenant-runtime-hub"', text)
        # The console-domains link moved into the included body partial (refactor);
        # verify the full chain: the shell includes the body, and the body links out.
        self.assertIn("tenant_runtime_configuration_hub_body.html", text)
        body_text = (
            shell.parent / "partials" / "tenant_runtime_configuration_hub_body.html"
        ).read_text(encoding="utf-8", errors="replace")
        self.assertIn("siteconfig:console_domains_hub", body_text)

    def test_backend_dashboard_role_home_shell(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "accounts" / "backend_dashboard.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-shell-role-home="backend"', text)
        self.assertIn('data-shell-role-ops="backend"', text)
        self.assertIn("shell_chrome_backend_system_indicators", text)

    def test_admin_nav_bridge_shell(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "components" / "admin_nav_bridge.html").read_text(encoding="utf-8", errors="replace")
        # nav-bridge value was renamed manager-admin → tenant-admin.
        self.assertIn('data-shell-nav-bridge="tenant-admin"', text)

    def test_marketplace_tenant_catalog_shell(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        text = (root / "templates" / "marketplace" / "tenant_app_catalog.html").read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-shell-marketplace="tenant-app-catalog"', text)
        self.assertIn("shell_chrome_marketplace_tenant_ops_strip", text)
        ops = (root / "templates" / "partials" / "shell_chrome_marketplace_tenant_ops_strip.html").read_text(
            encoding="utf-8", errors="replace"
        )
        self.assertIn('data-shell-marketplace-ops="activate-configure"', ops)


class StudioOsShellTests(unittest.TestCase):
    """Studio OS shell extends portal spine; no control-plane or marketing-only CSS."""

    def test_studio_shell_extends_portal_base_only(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "studio_os" / "shell.html"
        if not template.is_file():
            self.skipTest("templates/studio_os/shell.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertIn('{% extends "portal_base.html" %}', text)
        for forbidden in (
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ):
            self.assertNotIn(
                forbidden,
                text,
                f"Studio shell must not load other-surface CSS: {forbidden}",
            )

    def test_studio_shell_extrastyle_stays_studio_scoped(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        partial = root / "templates" / "studio_os" / "partials" / "shell_extrastyle.html"
        if not partial.is_file():
            self.skipTest("templates/studio_os/partials/shell_extrastyle.html not found")
        text = partial.read_text(encoding="utf-8", errors="replace")
        for forbidden in (
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ):
            self.assertNotIn(
                forbidden,
                text,
                f"Studio extrastyle must not load other-surface CSS: {forbidden}",
            )


class SurfaceThemesOnboardingTests(unittest.TestCase):
    """Onboarding data-surface on base.html is backed by surface theme tokens."""

    def test_surface_themes_defines_onboarding_plane(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        css = root / "static" / "css" / "surface-themes.css"
        if not css.is_file():
            self.skipTest("static/css/surface-themes.css not found")
        text = css.read_text(encoding="utf-8", errors="replace")
        self.assertIn('html[data-surface="onboarding"]', text)


class BaseHtmlDataSurfaceContractTests(unittest.TestCase):
    """base.html must expose data-surface for shared shell alignment (portal_base uses fixed tenant)."""

    def test_base_html_sets_data_surface_and_onboarding_paths(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "base.html"
        if not template.is_file():
            self.skipTest("templates/base.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertIn("{% load i18n %}", text)
        self.assertIn('data-surface="{% if request and', text)
        self.assertIn("/setup-studio/", text)
        self.assertIn("PUBLIC_BRAND_MODE", text)
        self.assertIn("onboarding{% elif PUBLIC_BRAND_MODE", text)
        self.assertIn("{% else %}tenant{% endif %}", text)
        self.assertLess(
            text.index("{% load i18n %}"),
            text.index("<!doctype html>"),
        )
        self.assertNotIn("{% load static i18n %}", text)


class ConfigControlCenterShellTests(unittest.TestCase):
    """Configuration Control Center (tenant + manager) templates expose a shared shell scope marker."""

    def test_console_domains_hubs_mark_config_control_surface(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        for relpath in (
            "templates/siteconfig/partials/console_domains_hub_body.html",
            "templates/siteconfig/partials/console_domains_hub_manager_body.html",
        ):
            p = root / relpath
            if not p.is_file():
                self.skipTest(f"{relpath} not found")
            text = p.read_text(encoding="utf-8", errors="replace")
            with self.subTest(path=relpath):
                self.assertIn('data-shell-surface="config-control-center"', text)


class OnboardWizardShellMarkerTests(unittest.TestCase):
    """Onboarding wizard extends base.html; mark root for shell inheritance audits."""

    def test_onboard_wizard_has_shell_page_marker(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "schools" / "onboard_wizard.html"
        if not template.is_file():
            self.skipTest("templates/schools/onboard_wizard.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertIn('data-shell-page="onboarding-wizard"', text)
        self.assertIn('{% extends "base.html" %}', text)


class ShellDataDashboardPageContractTests(unittest.TestCase):
    """Shared path→data-dashboard-page classifier loaded from one static file."""

    def test_shared_js_exists_and_bases_reference_it(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        js = root / "static" / "js" / "shell-data-dashboard-page.js"
        if not js.is_file():
            self.skipTest("static/js/shell-data-dashboard-page.js not found")
        self.assertGreater(js.stat().st_size, 200, "classifier should be non-trivial")
        rel = "js/shell-data-dashboard-page.js"
        for template_relpath in (
            "templates/portal_base.html",
            "templates/base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        ):
            p = root / template_relpath
            with self.subTest(path=template_relpath):
                text = p.read_text(encoding="utf-8", errors="replace")
                self.assertIn(rel, text, f"{template_relpath} must load the shared shell classifier")
        jt = js.read_text(encoding="utf-8", errors="replace")
        self.assertIn("/api/internal/metadata/", jt, "metadata UI lives under /api/internal/metadata/")
        self.assertIn("/reports/", jt, "reports app prefix classifier")
        self.assertIn("/setup-studio/", jt, "onboarding / setup studio classifier")


class ControlPlaneShellTests(unittest.TestCase):
    """Control-plane shell must not load marketing-only assets."""

    def test_control_plane_skeleton_does_not_load_marketing_only_css(self):
        """control_plane_skeleton.html must not reference marketing-shell.css or tokens-marketing.css."""
        root = Path(__file__).resolve().parent.parent.parent.parent
        template = root / "templates" / "control_plane_skeleton.html"
        if not template.is_file():
            self.skipTest("templates/control_plane_skeleton.html not found")
        text = template.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn(
            "marketing-shell.css",
            text,
            "Control plane must not load marketing-shell.css",
        )
        self.assertNotIn(
            "tokens-marketing.css",
            text,
            "Control plane must not load tokens-marketing.css",
        )
