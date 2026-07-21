from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    base_site = _read("templates/admin/base_site.html")
    base = _read("templates/admin/base.html")
    change_form = _read("templates/admin/change_form.html")
    change_list = _read("templates/admin/change_list.html")
    css_path = ROOT / "static/css/rmc-admin-django-canvas-contract.css"
    approval_css_path = ROOT / "static/css/rmc-admin-approval-surface-v15.css"

    if not css_path.is_file():
        errors.append("static/css/rmc-admin-django-canvas-contract.css is missing")
        css = ""
    else:
        css = css_path.read_text(encoding="utf-8")

    if not approval_css_path.is_file():
        errors.append("static/css/rmc-admin-approval-surface-v15.css is missing")
        approval_css = ""
    else:
        approval_css = approval_css_path.read_text(encoding="utf-8")

    contract_link = "rmc-admin-django-canvas-contract.css"
    if contract_link not in base_site:
        errors.append("templates/admin/base_site.html does not load the final Django canvas contract")
    if "?v=20260721-admin-os-v154" not in base_site:
        errors.append("Django canvas contracts must use the preview-parity-v13 cache bust for deployment visibility")
    if base_site.count(contract_link) != 1:
        errors.append("Django canvas contract must load exactly once")
    approval_link = "rmc-admin-approval-surface-v15.css"
    if base_site.count(approval_link) != 1:
        errors.append("Django approval v13 layout owner must load exactly once")
    if approval_link in base_site and base_site.rfind(approval_link) < base_site.rfind("admin-brand-resolved-tokens"):
        errors.append("Django approval v13 layout owner must load after resolved theme tokens")
    approval_n = re.sub(r"\s+", "", approval_css)
    if "minmax(0,1fr)minmax(9.2rem,17%)2.35rem" not in approval_n:
        errors.append("approval v13 CSS must own the operator main|17% rail|2.35rem tools grid")
    if "minmax(0,1fr)minmax(9.5rem,18%)2.35rem" not in approval_n:
        errors.append("approval v13 CSS must own the tenant main|18% rail|2.35rem tools grid")
    if "@media(max-width:1024px)" not in approval_n:
        errors.append("approval v13 CSS must stack every workspace at 1024px and below")
    if "table-layout:fixed!important" not in approval_n or "display:table!important" not in approval_n:
        errors.append("approval v13 CSS must preserve full native Django tables")
    if "position:static!important" not in approval_n:
        errors.append("approval v13 CSS must keep rails, tools and save actions in document flow")
    if change_list.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("change_list.html must mark exactly one primary fill panel")
    if change_form.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("change_form.html must mark exactly one primary fill panel")
    app_index = _read("templates/admin/app_index.html")
    if app_index.count("data-rmc-admin-index-canvas=") != 1:
        errors.append("app_index.html must have exactly one index canvas (nested grids cause the right void)")
    if app_index.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("app_index.html must mark exactly one primary fill panel")
    if base_site.count("rmc_theme_experience_dual_plane_styles.html") != 1:
        errors.append("Django admin theme-experience styles must load exactly once")
    head_only_partials = (
        "templates/partials/rmc_theme_meta.html",
        "templates/partials/rmc_social_meta.html",
        "templates/partials/rmc_shortcuts_i18n.html",
        "templates/partials/rmc_platform_chrome_styles.html",
        "templates/partials/rmc_platform_shell_beautify_styles.html",
        "templates/partials/rmc_sidebar_disclosure_contract_styles.html",
        "templates/partials/rmc_security_posture_layout_styles.html",
        "templates/partials/rmc_dashboard_corporate_os_styles.html",
        "templates/partials/rmc_authenticated_theme_tail.html",
        "templates/partials/rmc_theme_experience_dual_plane_styles.html",
        "templates/partials/rmc_lexicon_meta.html",
        "templates/partials/rmc_theme_personality_overrides.html",
    )
    for partial in head_only_partials:
        partial_text = _read(partial)
        if re.search(r"<\s*(?:body|main|div|section|aside|p|span)\b", partial_text, re.I):
            errors.append(
                f"{partial} is included from <head> and must not emit body-flow markup"
            )
    nav_bridge_source = _read("templates/components/admin_nav_bridge.html")
    if re.search(r"<link\b[^>]*\bstylesheet\b", nav_bridge_source, re.I):
        errors.append(
            "admin_nav_bridge.html must not emit a stylesheet from the body; load it in base_site <head>"
        )
    if base_site.count("admin-nav-bridge-tenant.css") != 1:
        errors.append("base_site must load the tenant nav stylesheet exactly once in <head>")
    if base_site.count("rmc-tour.css") != 1:
        errors.append("tour styles must load exactly once from base_site <head>")
    if "rmc_tour_css_in_head=True" not in base_site:
        errors.append("runtime tour partial must be told its CSS is already in <head>")
    if "portal_row_detail_drawer_bundle.html" in base_site or "rmc-portal-row-detail-drawer.css" in base_site:
        errors.append("Django admin must not mount the global row-detail fixed overlay")
    if "cp_context_drawer_shell.html" in base_site:
        errors.append("Django admin must not render the fixed Context overlay over page-aware tools")
    if "2026-07-20-v11-host-identity-contrast" not in css:
        errors.append("canvas contract must seal operator/tenant identity contrast")
    if "2026-07-20-v11-tenant-index-catalog" not in css:
        errors.append("canvas contract must seal tenant index catalog layout")
    if "2026-07-20-v11-responsive-stack" not in css:
        errors.append("canvas contract must seal tablet/mobile workspaces to one track")
    shared_catalog_css = _read("static/css/admin-platform-catalog.css")
    if ".cp-kpi-strip" not in shared_catalog_css or ".cp-catalog-card" not in shared_catalog_css:
        errors.append("shared admin catalog CSS must style tenant KPI and catalog primitives")
    if "_ai_copilot_rail.html" in base or "_operator_notebook.html" in base:
        errors.append("Django admin must use its page-aware tools column, not a second global copilot/notebook rail")
    if "rmc_operator_footer_civic.html" in base:
        errors.append("Django admin must not render the viewport-pinned operator civic footer over its workbench")
    if "admin_operator_steering_strip.html" in base or "rmc_operator_surface_strip" in base:
        errors.append("admin/base.html must not stack a global operator steering strip above page workspaces")
    if "admin_change_form_header.html" in change_form:
        errors.append("change_form.html must not stack the legacy secondary header above the command band")
    if "admin_changelist_header.html" in change_list:
        errors.append("change_list.html must not stack the legacy secondary header above the command band")
    if "data-rmc-admin-preview-url" in change_form:
        errors.append("shared change_form must not advertise an unimplemented generic preview URL")
    if "2026-07-19-full-fill-page-aware" not in css:
        errors.append("canvas contract must include 2026-07-19-full-fill-page-aware terminal block")
    if "2026-07-20-preview-parity-sot" not in css:
        errors.append("canvas contract must include 2026-07-20-preview-parity-sot (approval HTML grid)")
    if "minmax(9.2rem, 17%)" not in css and "minmax(9.2rem,17%)" not in css:
        errors.append("canvas contract must use operator approval rail minmax(9.2rem, 17%)")
    # Preview-parity verifier is the structural SOT vs approval HTML files.
    try:
        from scripts.verify_django_admin_preview_parity import main as _preview_parity_main
    except ImportError:
        import importlib.util

        _pp = ROOT / "scripts" / "verify_django_admin_preview_parity.py"
        spec = importlib.util.spec_from_file_location("verify_django_admin_preview_parity", _pp)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _preview_parity_main = mod.main
    if _preview_parity_main() != 0:
        errors.append("verify_django_admin_preview_parity.py failed (approval HTML != live shell)")

    # tools-no-span-explode: span 20/40 invents empty grid tracks (stripe / dark-bar bug)
    if re.search(r"data-rmc-django-tools[\s\S]{0,200}grid-row:\s*3\s*/\s*span\s*(20|40)", css):
        errors.append("canvas contract must NOT use grid-row span 20/40 on [data-rmc-django-tools] (stripe bug)")
    css_nocomment = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if re.search(r"grid-row:\s*\d+", css_nocomment):
        errors.append("canvas contract must NOT hardcode numeric grid-row (use auto — empty tracks cause stripe/right-void)")
    if "2026-07-19-tools-no-span-explode" not in css:
        errors.append("canvas contract must include 2026-07-19-tools-no-span-explode terminal seal")
    if "2026-07-20-action-nowrap" not in css:
        errors.append("canvas contract must include 2026-07-20-action-nowrap save-bleed seal")
    if "2026-07-20-grid-row-auto-fullfill" not in css:
        errors.append("canvas contract must include 2026-07-20-grid-row-auto-fullfill terminal seal")
    if "2026-07-20-platformwide-no-container" not in css:
        errors.append("canvas contract must include 2026-07-20-platformwide-no-container seal")
    if "2026-07-20-miss-nothing-label-wrap" not in css:
        errors.append("canvas contract must include 2026-07-20-miss-nothing-label-wrap seal")
    if "data-rmc-admin-html','unfold'" not in base_site and 'data-rmc-admin-html","unfold"' not in base_site:
        errors.append("base_site must set data-rmc-admin-html=unfold in pre-paint head script")
    content_m = re.search(r'<div id="content"[^>]*>', base)
    if content_m and ("mx-auto" in content_m.group(0) or re.search(r"\bcontainer\b", content_m.group(0))):
        errors.append("admin/base.html #content must not use Tailwind container or mx-auto")
    # label/.form-row must not be subjects of overflow-wrap:anywhere
    css_nocomment2 = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    if re.search(
        r":is\([^)]*\blabel\b[^)]*\)\s*\{[^}]*overflow-wrap\s*:\s*anywhere",
        css_nocomment2,
        re.S,
    ) or re.search(
        r":is\([^)]*\.form-row\b[^)]*\)\s*\{[^}]*overflow-wrap\s*:\s*anywhere",
        css_nocomment2,
        re.S,
    ):
        errors.append("canvas contract must not set overflow-wrap:anywhere on label/.form-row")
    if re.search(r"\.rmc-django-action\s*\{[^}]*overflow-wrap:\s*anywhere", css):
        errors.append("canvas contract must not set overflow-wrap:anywhere on .rmc-django-action")
    if "a.skip-link:not(:focus)" not in css and "a.skip-link:not(:focus):not(:focus-visible)" not in css:
        errors.append("canvas contract must clip a.skip-link until focus (not only skip-link-theme)")
    # Tenant /admin/ does not load Bootstrap — skip links must use design-tokens .skip-link.
    if 'class="skip-link"' not in base or "skip-link-theme" in base or "visually-hidden-focusable" in base:
        errors.append("admin/base.html canvas skip link must use class=skip-link only (no Bootstrap visually-hidden-focusable)")
    # Unfold injects nav_global into tab_actions — never put skip-link there.
    nav_global_block = re.search(
        r"\{%\s*block\s+nav-global\s*%\}(.*?)\{%\s*endblock",
        base_site,
        re.S,
    )
    if nav_global_block and "skip-link" in nav_global_block.group(1):
        errors.append("admin/base_site.html nav-global must be empty (skip-link must not enter Unfold tab_actions)")
    if 'data-rmc-tenant-admin-chrome="1"' not in base:
        errors.append("admin/base.html must mark tenant shell header for single school chrome")
    if 'include "components/admin_nav_bridge.html"' not in base and "admin_nav_bridge.html" not in base:
        errors.append("admin/base.html must mount admin_nav_bridge in the tenant shell header")
    if "unfold/helpers/header.html" in base and "is_manager_host" not in base[base.find("rmc-app-shell__header") : base.find("rmc-app-shell__header") + 800]:
        # Tenant must not render a second Unfold title bar alongside the school topbar.
        header_slice = base[base.find("rmc-app-shell__header") : base.find("rmc-app-shell__header") + 900]
        if "unfold/helpers/header.html" in header_slice and "admin_nav_bridge" in header_slice:
            errors.append("admin/base.html tenant header must not stack Unfold header with nav bridge")
    tokens = _read("static/css/design-tokens.css")
    if ".visually-hidden-focusable:not(:focus)" not in tokens:
        errors.append("design-tokens.css must define .visually-hidden-focusable (tenant admin has no Bootstrap)")
    if "bootstrap-icons.min.css" not in base_site:
        errors.append("admin/base_site.html must load bootstrap-icons for tenant admin CTAs")
    if "manager-control-plane.css" in base_site:
        # Must be gated — crude check: appear only inside is_manager_host branch near the link
        mcp_idx = base_site.find("manager-control-plane.css")
        gate_window = base_site[max(0, mcp_idx - 200) : mcp_idx]
        if "is_manager_host" not in gate_window:
            errors.append("manager-control-plane.css must be gated to is_manager_host (no tenant bleed)")
    for admin_html in (
        "templates/admin/app_index.html",
        "templates/admin/change_list.html",
        "templates/admin/includes/admin_change_form_mode_panels.html",
        "templates/admin/object_history.html",
        "templates/admin/delete_confirmation.html",
    ):
        if "Tenant scoped" in _read(admin_html):
            errors.append(f"{admin_html} must not say Tenant scoped (use This school only)")
    app_index = _read("templates/admin/app_index.html")
    if "This school only" not in app_index or 'data-rmc-admin-archetype="dossier"' not in app_index:
        errors.append("admin/app_index.html must use dossier archetype with This school only host voice")
    banner = _read("templates/admin/includes/tenant_admin_decision_banner.html")
    if "studio_os" in banner or "Operator workflow" in banner or "Decision console" in banner:
        errors.append("tenant_admin_decision_banner must be school-only (no Studio / operator / Decision console)")
    if "School configuration" not in banner:
        errors.append("tenant_admin_decision_banner must use School configuration framing")
    # v15: decision banner removed from list/form fold-1 (education via ⓘ tips)
    if "tenant_admin_decision_banner.html" in base:
        errors.append("admin/base.html must not inject tenant_admin_decision_banner on list/form (v15 zero fluff)")
    history = _read("templates/admin/object_history.html")
    delete = _read("templates/admin/delete_confirmation.html")
    if 'data-rmc-django-workspace="object-history"' not in history:
        errors.append("object_history.html must use rmc-django-workspace markers")
    if 'data-rmc-admin-archetype="audit"' not in history:
        errors.append("object_history.html must set data-rmc-admin-archetype=audit")
    if 'data-rmc-django-workspace="delete-confirm"' not in delete:
        errors.append("delete_confirmation.html must use rmc-django-workspace markers")
    if 'data-rmc-admin-archetype="decide"' not in delete:
        errors.append("delete_confirmation.html must set data-rmc-admin-archetype=decide")
    app_list = _read("templates/admin/app_list.html")
    # Report Library via Studio must be manager-only
    studio_report = app_list.find("studio_os:output")
    if studio_report >= 0:
        before = app_list[max(0, studio_report - 120) : studio_report]
        if "is_manager_host" not in before:
            errors.append("admin/app_list.html Report Library (studio_os:output) must be gated to is_manager_host")
    workspace_10x = _read("static/css/rmc-admin-workspace-10x.css")
    for m in re.finditer(r"^[^/\n]*width:\s*max-content", workspace_10x, re.M):
        errors.append(f"rmc-admin-workspace-10x.css still has active width:max-content: {m.group(0).strip()[:80]}")
    nav_bridge = _read("templates/components/admin_nav_bridge.html")
    if "Config center" not in nav_bridge or "Feature control" not in nav_bridge:
        errors.append("admin_nav_bridge tenant escapes must include Config center and Feature control")
    if "Back to Backend" in nav_bridge:
        errors.append("admin_nav_bridge must not use Back to Backend as primary tenant escape (use Config/Feature/Portal)")
    submit_line = _read("templates/admin/submit_line.html")
    if 'data-rmc-save-compact="1"' not in submit_line or "rmc-django-save-split" not in submit_line:
        errors.append("submit_line.html must implement compact Save split (Save + menu)")
    tools = _read("templates/admin/includes/admin_workspace_tools.html")
    if 'surface == "change-list"' not in tools or 'surface == "change-form"' not in tools:
        errors.append("admin_workspace_tools.html must be page/surface-aware")
    if 'surface == "admin-index"' not in tools and "admin-index" not in tools:
        # Index tools omit + / Filters by not matching list/form branches — ensure no inert primary +
        if "aria-hidden=\"true\">+</span>" in tools:
            errors.append("admin_workspace_tools must not render inert + on every surface")
    live_css = _read("static/css/rmc-admin-changelist-live.css")
    if re.search(r"width:\s*max-content", live_css):
        errors.append("rmc-admin-changelist-live.css must not use width:max-content on result tables")
    # No active max-content / false label|value grids (comments mentioning them are OK)
    for m in re.finditer(r"^[^/\n]*width:\s*max-content", css, re.M):
        errors.append(f"canvas contract still has active width:max-content rule: {m.group(0).strip()[:80]}")
    for m in re.finditer(r"^[^/\n]*0\.(24|32)fr", css, re.M):
        errors.append(f"canvas contract still has active false label|value fr track: {m.group(0).strip()[:80]}")
    login = _read("templates/auth/tenant_admin_login.html")
    if "Tenant Administration" in login:
        errors.append("tenant_admin_login.html must use school configuration identity")
    if "Configuration &amp; records" not in login and "Configuration & records" not in login:
        errors.append("tenant_admin_login.html must say Configuration & records")
    rail_py = _read("apps/siteconfig/admin_page_aware_rail.py")
    if "Tenant boundary" in rail_py:
        errors.append("admin_page_aware_rail.py must not use Tenant boundary (use School boundary)")
    if "School boundary" not in rail_py:
        errors.append("admin_page_aware_rail.py must define School boundary")
    if "rmc_tour_bootstrap.html" not in base_site and "rmc-info-tag.js" not in base_site:
        errors.append("admin/base_site.html must load rmc-info-tag JS (via rmc_tour_bootstrap)")
    metrics = (ROOT / "templates/admin/includes/admin_workspace_metrics_strip.html").read_text(encoding="utf-8")
    for banned in ("Canvas", "Form cap", "100%", "Save</span><b>{% trans \"Static\""):
        if banned in metrics:
            errors.append(f"admin metrics strip still contains fluff token: {banned}")
            break
    if "rmc-django-metrics--compact" not in metrics:
        errors.append("admin metrics strip must use compact honest metrics")
    if "rmc_info_tag" not in metrics:
        errors.append("admin metrics strip must educate via rmc_info_tag")
    if f'{contract_link}\' %}}" media="print"' in base_site:
        errors.append("Django canvas contract must not be lazy media=print/onload CSS")
    if contract_link in base_site and "rmc_theme_experience_dual_plane_styles.html" in base_site:
        if base_site.rfind(contract_link) < base_site.rfind("rmc_theme_experience_dual_plane_styles.html"):
            errors.append("Django canvas contract must load after preview/theme inline styles")
    if "{% block bodyclass %}" not in base_site:
        errors.append("templates/admin/base_site.html must server-render admin body classes")
    if "admin-manager-shell control-plane-shell cp-surface" not in base_site:
        errors.append("templates/admin/base_site.html missing server-rendered operator admin body classes")
    if "admin-premium-shell" not in base_site:
        errors.append("templates/admin/base_site.html missing server-rendered tenant admin body class")
    if "data-rmc-cp-scroll', 'canvas'" not in base_site:
        errors.append("templates/admin/base_site.html must set data-rmc-cp-scroll=canvas for manager and tenant admin")
    if base_site.count("data-rmc-cp-scroll', 'canvas'") < 2:
        errors.append("templates/admin/base_site.html must set data-rmc-cp-scroll=canvas on BOTH manager and tenant branches")
    if "rmc-app-shell--fluid" in base and "rmc-app-shell--fluid{% if" not in base:
        # Fluid must not appear as an unconditional tenant class (sidebar-over-canvas trap).
        if re.search(r"rmc-app-shell--fluid(?![^\n]*popup)", base) and "{% else %} rmc-app-shell--fluid" in base:
            errors.append("admin/base.html must not use rmc-app-shell--fluid for tenant Django admin (use canvas scroll parity)")
    if "rmc-app-shell--fluid{% endif %}" in base or "{% else %} rmc-app-shell--fluid{% endif %}" in base:
        errors.append("admin/base.html must not attach rmc-app-shell--fluid to tenant Django admin shell")
    if "cp-admin-canvas-main" not in base:
        errors.append("admin/base.html must mark #cp-main-content with cp-admin-canvas-main for canvas scroll")
    scroll_css = _read("static/css/rmc-backoffice-scroll-10x.css")
    if "body.admin-premium-shell[data-rmc-cp-scroll=\"canvas\"]" not in scroll_css:
        errors.append("rmc-backoffice-scroll-10x.css must include tenant admin-premium-shell canvas scroll rules")
    if "tenant-scroll-parity" not in css:
        errors.append("rmc-admin-django-canvas-contract.css must include tenant-scroll-parity overflow:visible terminal block")
    if "field-grid-save" not in css:
        errors.append("rmc-admin-django-canvas-contract.css must include field-grid-save smart-grid + form-panel save block")
    if ".form-rows > .form-row" not in css or "grid-column: span 6" not in css:
        errors.append("canvas contract must place .form-rows > .form-row on a half-width smart grid (span 6)")
    if "data-rmc-django-actions-in-panel" not in css:
        errors.append("canvas contract must style [data-rmc-django-actions-in-panel] as form-panel footer")
    if "balanced-canvas-no-bleed" not in css and "parity-close" not in css:
        errors.append("rmc-admin-django-canvas-contract.css must include balanced-canvas / parity-close terminal block")
    if "page-aware-rail" not in css or "rmc-django-rail-facts" not in css:
        errors.append("canvas contract must include page-aware-rail facts styling")
    if "data-rmc-django-tools" not in css:
        errors.append("canvas contract must style [data-rmc-django-tools] 48px tools column")
    if "data-rmc-django-metrics" not in css:
        errors.append("canvas contract must style [data-rmc-django-metrics] workspace metrics")
    if "data-rmc-django-table-pagination" not in css:
        errors.append("canvas contract must style in-panel table pagination")
    if 'data-rmc-admin-index-canvas="operator"' not in css and '[data-rmc-admin-index-canvas="operator"]' not in css:
        errors.append("canvas contract must style operator index canvas rail layout")
    change_form = change_form  # keep name in scope below

    reveal_js = _read("static/js/rmc-reveal.js")
    if "admin-premium-shell" not in reveal_js or "rmc-app-shell__canvas" not in reveal_js:
        errors.append("rmc-reveal.js must treat Django admin shells as immediate-reveal + know canvas scroll roots")
    paginator_js = _read("static/js/rmc-tenant-surface-paginator.js")
    mark_fn = paginator_js[paginator_js.find("function markOversizePanels") : paginator_js.find("function markOversizePanels") + 900]
    if "admin-premium-shell" not in mark_fn:
        errors.append("rmc-tenant-surface-paginator.js markOversizePanels must skip Django admin (admin-premium-shell)")

    if 'data-rmc-app-shell-host="{% if is_manager_host %}manager{% else %}tenant{% endif %}"' not in base:
        errors.append("admin/base.html missing explicit manager/tenant shell host marker")
    if 'data-rmc-admin-canvas-contract="intelligent-full-width"' not in base:
        errors.append("admin/base.html missing intelligent full-width canvas marker")
    if 'data-rmc-admin-canvas-host="{% if is_manager_host %}operator{% else %}tenant{% endif %}"' not in base:
        errors.append("admin/base.html missing explicit operator/tenant canvas host marker")
    marker_index = base.find('data-rmc-admin-canvas-contract="intelligent-full-width"')
    manager_guard_index = base.rfind("{% if is_manager_host %}", 0, marker_index)
    manager_guard_end_index = base.rfind("{% endif %}", 0, marker_index)
    if manager_guard_index > manager_guard_end_index:
        errors.append("admin/base.html must not wrap the full-canvas contract in is_manager_host only")
    if "rmc-tenant-admin-page-body" not in base:
        errors.append("admin/base.html missing tenant admin full-canvas page body")
    if 'data-rmc-admin-content="canvas-first"' not in base:
        errors.append("admin/base.html missing canvas-first content marker")
    if 'data-rmc-admin-form-contract="premium-form-frame"' not in change_form:
        errors.append("admin/change_form.html missing premium form frame marker")
    if 'data-rmc-django-workspace="change-form"' not in change_form:
        errors.append("admin/change_form.html missing structural change-form workspace marker")
    if 'data-rmc-django-command-band="change-form"' not in change_form:
        errors.append("admin/change_form.html missing structural change-form command band")
    if 'data-rmc-django-view-toggle="1"' in change_form:
        errors.append("admin/change_form.html must not ship Form/Audit view toggle (v15)")
    if 'data-rmc-django-view-mode="form"' not in change_form:
        errors.append("admin/change_form.html missing default view-mode marker")
    if "admin_change_form_mode_panels.html" in change_form:
        errors.append("admin/change_form.html must not include mode panels (v15 — Audit via History/Save)")
    if 'rmc-django-form-panel' not in change_form:
        errors.append("admin/change_form.html missing structural form panel class")
    if 'data-rmc-django-form-body="1"' not in change_form:
        errors.append("admin/change_form.html missing structural form body marker")
    if 'data-rmc-django-actions-slot="1"' not in change_form:
        errors.append("admin/change_form.html must keep static save row inside the workbench (actions-slot)")
    if 'data-rmc-django-actions-in-panel="1"' not in change_form:
        errors.append("admin/change_form.html must nest save actions inside the form panel (actions-in-panel)")
    # G2: actions-slot must sit inside #content-main / form panel, not after the side rail.
    content_main_idx = change_form.find('id="content-main"')
    actions_idx = change_form.find('data-rmc-django-actions-slot="1"')
    rail_idx = change_form.find("admin_change_form_rail.html")
    if content_main_idx < 0 or actions_idx < 0:
        errors.append("admin/change_form.html missing content-main or actions-slot markers")
    elif not (content_main_idx < actions_idx and (rail_idx < 0 or actions_idx < rail_idx)):
        errors.append("admin/change_form.html actions-slot must be nested inside form panel before the side rail include")
    if 'data-rmc-admin-form-scope="{% if is_manager_host %}operator{% else %}tenant{% endif %}"' not in change_form:
        errors.append("admin/change_form.html missing operator/tenant form scope marker")
    if 'data-rmc-admin-surface="smart-form"' not in change_form:
        errors.append("admin/change_form.html missing smart form surface marker")
    if "admin_preview_card_stage.html" in change_form:
        errors.append("admin/change_form.html must not include staged admin_preview_card_stage.html")
    rail = _read("templates/admin/includes/admin_change_form_rail.html")
    if "admin_preview_card_stage.html" in rail or 'data-rmc-django-rail-preview="1"' in rail or "rmc-django-preview-card" in rail:
        errors.append("admin_change_form_rail.html must not include staged Live preview")
    if "admin_page_aware_rail" not in rail and "admin_page_aware_rail_cards" not in rail:
        errors.append("admin_change_form_rail.html must include page-aware rail cards")
    if 'data-rmc-django-rail-page-aware="1"' not in rail:
        errors.append("admin_change_form_rail.html must mark data-rmc-django-rail-page-aware")
    cl_rail = _read("templates/admin/includes/admin_changelist_rail.html")
    if "admin_page_aware_rail" not in cl_rail:
        errors.append("admin_changelist_rail.html must include page-aware rail cards")
    if 'data-rmc-django-view="preview"' in change_form:
        errors.append("admin/change_form.html must not expose a Preview view toggle without a real preview")
    if "rmc-django-view-toggle" in change_form or "admin_change_form_mode_panels.html" in change_form:
        errors.append("admin/change_form.html must not ship Form/Audit toggle chrome (v15 Admin OS)")
    metrics = _read("templates/admin/includes/admin_workspace_metrics_strip.html")
    if '{% trans "Stage" %}' in metrics or ">Stage<" in metrics:
        errors.append("admin_workspace_metrics_strip.html must not claim Preview/Stage when preview is removed")
    tools = _read("templates/admin/includes/admin_workspace_tools.html")
    if 'data-rmc-django-view-jump="preview"' in tools or "data-rmc-django-preview-open" in tools:
        errors.append("admin_workspace_tools.html must not expose staged preview tools")
    if "data-rmc-django-rail-live" not in _read("templates/admin/includes/admin_page_aware_rail_cards.html"):
        errors.append("admin_page_aware_rail_cards.html must mark live-rail cards (v15 I9)")
    if 'data-rmc-django-rail-page="1"' in _read("templates/admin/includes/admin_page_aware_rail_cards.html"):
        errors.append("admin_page_aware_rail_cards.html must not ship boundary manifesto card (v15 I9)")
    if "rmc-admin-disclosure" not in _read("static/js/rmc-admin-workspace.js"):
        errors.append("rmc-admin-workspace.js M2M condensation must use rmc-admin-disclosure (v15 I6)")
    if "admin_workspace_metrics_strip.html" in change_form or "admin_workspace_metrics_strip.html" in change_list:
        errors.append("change_form/change_list must not include metrics strip (v15 zero fluff)")
    if "admin_workspace_tools.html" not in change_form:
        errors.append("admin/change_form.html must include 48px workspace tools")
    if "admin_workspace_tools.html" not in change_list:
        errors.append("admin/change_list.html must include 48px workspace tools")
    if 'data-rmc-admin-archetype="edit"' not in change_form:
        errors.append("admin/change_form.html must set data-rmc-admin-archetype=edit")
    if 'data-rmc-admin-archetype="scan"' not in change_list:
        errors.append("admin/change_list.html must set data-rmc-admin-archetype=scan")
    if 'data-rmc-django-table-pagination="1"' not in change_list:
        errors.append("admin/change_list.html must nest pagination inside table panel")
    if "{% block pagination %}" in change_list[change_list.find("{% block footer %}"):] if "{% block footer %}" in change_list else "":
        footer = change_list[change_list.find("{% block footer %}"):]
        if "pagination.html" in footer:
            errors.append("admin/change_list.html must not keep pagination in footer (G6)")
    header_cf = _read("templates/admin/includes/admin_change_form_header.html")
    if 'data-rmc-admin-toolbar-only="1"' not in header_cf:
        errors.append("admin_change_form_header.html must be toolbar-only (no duplicate H1)")
    if "<h1" in header_cf:
        errors.append("admin_change_form_header.html must not render an H1 (G9)")
    header_cl = _read("templates/admin/includes/admin_changelist_header.html")
    if 'data-rmc-admin-toolbar-only="1"' not in header_cl:
        errors.append("admin_changelist_header.html must be toolbar-only (no duplicate H1)")
    if "<h1" in header_cl:
        errors.append("admin_changelist_header.html must not render an H1 (G9)")
    workspace_js = _read("static/js/rmc-admin-workspace.js")
    if 'if (mode === "preview") mode = "form";' not in workspace_js:
        errors.append("rmc-admin-workspace.js must refuse staged preview mode (map to form)")
    innovations_js = _read("static/js/rmc-admin-os-innovations.js")
    if "initSelectionGravity" not in innovations_js or "initKeymap" not in innovations_js:
        errors.append("rmc-admin-os-innovations.js must ship selection gravity + keymap (v15 waves 2–4)")
    if "rmc-admin-os-innovations.js" not in base_site:
        errors.append("base_site must load rmc-admin-os-innovations.js after workspace.js")
    if "rmc-admin-model-policy.js" not in base_site:
        errors.append("base_site must load rmc-admin-model-policy.js (v15 I11)")
    if 'data-rmc-admin-keymap-open="1"' not in tools:
        errors.append("admin_workspace_tools.html must use ? for keymap (data-rmc-admin-keymap-open)")
    if 'data-rmc-command-bar-trigger="1"' in tools and 'title="{% trans \'Command palette\' %}"' in tools:
        errors.append("admin_workspace_tools.html ? must not open command palette (use keymap)")
    try:
        from scripts.verify_admin_os_three_click_sla import main as _three_click_main
    except ImportError:
        import importlib.util

        _tc = ROOT / "scripts" / "verify_admin_os_three_click_sla.py"
        spec = importlib.util.spec_from_file_location("verify_admin_os_three_click_sla", _tc)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
        _three_click_main = mod.main
    if _three_click_main() != 0:
        errors.append("verify_admin_os_three_click_sla.py failed (Discover catalog must be ≤3-click reachable)")
    if 'data-rmc-admin-pins="1"' not in _read("templates/admin/index_superadmin.html"):
        errors.append("index_superadmin.html must mount pin/recent row (v15 I7)")
    if 'data-rmc-admin-pins="1"' not in _read("templates/admin/index_tenant.html"):
        errors.append("index_tenant.html must mount pin/recent row (v15 I7)")
    if 'data-rmc-admin-selection-gravity="1"' not in change_list:
        errors.append("change_list.html must mark selection gravity root (v15 I1)")
    if 'data-rmc-admin-row-peek="1"' not in change_list:
        errors.append("change_list.html must mark row peek root (v15 I2)")
    if 'data-rmc-admin-section-radar="1"' not in change_form:
        errors.append("change_form.html must mark section radar root (v15 I4)")
    if 'data-rmc-admin-focus-root="1"' not in change_form:
        errors.append("change_form.html must mark focus mode root (v15 I5)")
    if "is-bulk-active" not in approval_css or "rmc-admin-os-sheet" not in approval_css:
        errors.append("approval v15 CSS must include waves 2–4 innovation styles")
    # setViewMode may remain for legacy; Form/Audit chrome is banned in templates (v15)
    if 'data-rmc-admin-table-contract="native-table-scroll"' not in change_list:
        errors.append("admin/change_list.html missing native table scroll marker")
    if 'data-rmc-django-workspace="change-list"' not in change_list:
        errors.append("admin/change_list.html missing structural change-list workspace marker")
    if 'data-rmc-django-command-band="change-list"' not in change_list:
        errors.append("admin/change_list.html missing structural change-list command band")
    if 'data-rmc-django-table-panel="1"' not in change_list:
        errors.append("admin/change_list.html missing structural table panel marker")
    if 'data-rmc-admin-surface="smart-changelist"' not in change_list:
        errors.append("admin/change_list.html missing smart changelist surface marker")
    if "admin_changelist_rail.html" not in change_list:
        errors.append("admin/change_list.html missing changelist context rail include")
    if 'cp-changelist-live' not in change_list:
        errors.append("admin/change_list.html must apply cp-changelist-live to tenant and operator")

    required_css_tokens = (
        "body:is(.admin-manager-shell, .admin-premium-shell)",
        "[data-rmc-shell-root=\"django-admin\"]",
        "[data-rmc-admin-table-contract=\"native-table-scroll\"]",
        "--rmc-backoffice-form-max",
        "Specificity hardening",
        "Intelligent full-canvas revamp",
        "data-rmc-admin-canvas-contract=\"intelligent-full-width\"",
        "data-rmc-admin-canvas-host",
        "data-rmc-admin-content=\"canvas-first\"",
        "data-rmc-admin-surface=\"smart-form\"",
        "data-rmc-admin-surface=\"smart-changelist\"",
        "data-rmc-admin-surface=\"smart-index\"",
        "data-rmc-django-workspace=\"admin-index\"",
        "data-rmc-admin-index-canvas",
        "2026-07-17 intelligent-index",
        "2026-07-17 second-audit closure",
        "2026-07-17 residual closure",
        "rmc-django-view-toggle",
        "data-rmc-django-changelist-rail",
        "data-rmc-django-actions-slot",
        "parity-close",
        "balanced-canvas-no-bleed",
        "page-aware-rail",
        "guided-app-index-canvas",
        "rmc-django-rail-facts",
        "rmc-django-guided-checklist",
        "data-rmc-django-tools",
        "data-rmc-django-metrics",
        "data-rmc-django-table-pagination",
        '[data-rmc-admin-index-canvas="operator"]',
        "rmc-tenant-admin-page-body",
        "container-type: inline-size",
        "Final platform-wide/tenant-wide Django sweep",
        "Structural canvas closure, 2026-07-11",
        "Production hardening, 2026-07-12",
        "HTML-gate independent closure, 2026-07-13",
        "rmc-django-workspace",
        "rmc-django-command-band",
        "[data-rmc-django-command-band]",
        "visibility: visible !important",
        "opacity: 1 !important",
        "grid-template-columns: repeat(12, minmax(0, 1fr)) !important",
        "grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr)) !important",
        "grid-column: span 6 !important",
        "rmc-django-form-panel",
        "rmc-django-form-body",
        "rmc-django-side-panel",
        "rmc-django-actions",
        "rmc-django-table-panel",
        "data-rmc-django-workspace=\"change-form\"",
        "data-rmc-django-workspace=\"change-list\"",
        "reportcard-builder-preview",
        "theme-preview-section",
        "rmc-admin-changeform-pagehead",
        "rmc-admin-changelist-pagehead",
        "rmc-rail-card",
        "#content-main.cp-form-frame[data-rmc-admin-form-contract=\"premium-form-frame\"]",
        "rmc-admin-workspace",
        "data-rmc-admin-form-contract=\"premium-form-frame\"",
        "grid-template-columns: repeat(auto-fit",
        "position: static !important",
        "data-change-list-filter",
        "display: table !important",
        "display: table-row !important",
        "display: table-cell !important",
        "overflow-x: auto !important",
        "rmc-preview-iframe",
        "iframe[data-rmc-preview-frame]",
        "admin-premium-shell",
        "admin-manager-shell",
        "[data-rmc-admin-canvas-contract=\"intelligent-full-width\"]",
        "[data-rmc-shell-root=\"django-admin\"] [data-rmc-admin-canvas-contract=\"intelligent-full-width\"]",
        "[data-rmc-shell-root=\"django-admin\"] [data-rmc-django-workspace=\"change-form\"]",
        "[data-rmc-shell-root=\"django-admin\"] [data-rmc-django-side-panel]",
    )
    for token in required_css_tokens:
        if token not in css:
            errors.append(f"rmc-admin-django-canvas-contract.css missing {token}")

    admin_template_errors = _audit_admin_template_overrides()
    errors.extend(admin_template_errors)
    errors.extend(_audit_intelligent_index_surfaces())

    if errors:
        print("DJANGO_ADMIN_CANVAS_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("DJANGO_ADMIN_CANVAS_CONTRACT_PASS")
    print("  scope: operator + tenant Django admin")
    print("  contract: full-width canvas, native tables, stable forms, preview sizing")
    return 0


def _audit_intelligent_index_surfaces() -> list[str]:
    errors: list[str] = []
    tenant_index = _read("templates/admin/index_tenant.html")
    operator_index = _read("templates/admin/index_superadmin.html")
    admin_py = _read("config/admin.py")
    nav_bridge = _read("templates/components/admin_nav_bridge.html")

    for token in (
        'data-rmc-admin-surface="smart-index"',
        'data-rmc-django-workspace="admin-index"',
        'data-rmc-django-command-band="admin-index"',
        'data-rmc-admin-archetype="discover"',
        'data-rmc-admin-index-canvas="tenant"',
        "rmc-admin-catalog-index",
        "Configuration &amp; records",
        "admin_catalog",
        "rmc_info_tag",
        "This school only",
    ):
        if token not in tenant_index:
            errors.append(f"templates/admin/index_tenant.html missing intelligent index token: {token}")

    if "Raw model CRUD only" in tenant_index:
        errors.append("templates/admin/index_tenant.html must not use the empty Raw model CRUD-only hero")
    if "Tenant model catalog" in tenant_index or "Tenant Administration" in tenant_index:
        errors.append("templates/admin/index_tenant.html must use school configuration engine identity (not Tenant Administration)")
    if "cp-steering" in tenant_index or "admin_index_context_rail.html" in tenant_index:
        errors.append("templates/admin/index_tenant.html Discover must not include steering/rail fluff")
    if "cp-kpi-strip" in tenant_index:
        errors.append("templates/admin/index_tenant.html Discover must not include KPI strip fluff")

    if "def index(self, request, extra_context=None):" not in admin_py:
        errors.append("config/admin.py TenantAdminSite must override index for catalog context")
    if "build_platform_admin_catalog" not in admin_py:
        errors.append("config/admin.py must build admin_catalog for tenant index")
    # TenantAdminSite.index must call build_platform_admin_catalog (not only PlatformAdminSite)
    tenant_site_slice = admin_py.split("class TenantAdminSite", 1)[-1].split("class PlatformAdminSite", 1)[0]
    if "build_platform_admin_catalog" not in tenant_site_slice:
        errors.append("TenantAdminSite.index must build admin_catalog via build_platform_admin_catalog")
    if "tenant_admin_engine" not in tenant_site_slice:
        errors.append("TenantAdminSite.each_context must mark tenant_admin_engine for school identity")

    # School host must never inject operator control-plane chrome into /admin/
    if "{% operator_console_strip" in nav_bridge or "{%operator_console_strip" in nav_bridge:
        errors.append("admin_nav_bridge must not inject operator_console_strip on tenant /admin/")
    if "PRIMARY_CONTROL_PLANE_NAV and not is_manager_host" in nav_bridge:
        errors.append("admin_nav_bridge must not render PRIMARY_CONTROL_PLANE_NAV on tenant hosts")
    if "control_plane_primary_nav.html" in nav_bridge and "is_manager_host" not in nav_bridge.split("control_plane_primary_nav.html")[0][-200:]:
        # Soft: include of CP primary nav on tenant branch is forbidden
        pass
    if "{% include \"partials/control_plane_primary_nav.html\" %}" in nav_bridge:
        errors.append("admin_nav_bridge must not include control_plane_primary_nav on tenant hosts")
    if "Configuration &amp; records" not in nav_bridge and "Configuration & records" not in nav_bridge:
        errors.append("admin_nav_bridge tenant identity must say Configuration & records")

    if 'data-rmc-admin-catalog-index="1"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html missing catalog index marker")
    if 'data-rmc-django-command-band="admin-index"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html missing admin-index command band")
    if 'data-rmc-admin-archetype="discover"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html must set discover archetype")
    if 'data-rmc-admin-index-canvas="operator"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html missing operator index canvas wrapper")
    if "cp-steering" in operator_index or "admin_index_context_rail.html" in operator_index:
        errors.append("templates/admin/index_superadmin.html Discover must not include steering/rail fluff")
    if "admin_v1_index_surface_previews.html" not in operator_index:
        errors.append("templates/admin/index_superadmin.html must include live surface sections")
    if "admin_workspace_tools.html" in operator_index or "admin_workspace_tools.html" in tenant_index:
        errors.append("Discover indexes must not include tools column (v15 1-col)")
    if "feature_control_panel" not in tenant_index:
        errors.append("templates/admin/index_tenant.html must restore Feature control CTA")
    if "admin_catalog_section_nav_items" not in operator_index and "rmc-admin-sec-tags" not in operator_index:
        errors.append("operator index must expose on-page section nav for restored sections")

    base = _read("templates/admin/base.html")
    if "tenant_admin_decision_banner.html" in base:
        errors.append("admin/base.html must not inject tenant_admin_decision_banner (v15 zero fluff)")
    if 'data-rmc-django-workspace="delete-confirm"' not in _read("templates/admin/delete_selected_confirmation.html"):
        errors.append("delete_selected_confirmation.html must use rmc-django-workspace delete-confirm markers")
    if 'data-rmc-admin-archetype="decide"' not in _read("templates/admin/delete_selected_confirmation.html"):
        errors.append("delete_selected_confirmation.html must set decide archetype")

    # Continuous leftovers loop gate (operator + tenant left-behind surfaces)
    try:
        from scripts.audit_django_admin_surface_leftovers import main as leftovers_main
    except Exception:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "audit_django_admin_surface_leftovers",
            ROOT / "scripts" / "audit_django_admin_surface_leftovers.py",
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        leftovers_main = mod.main
    if leftovers_main() != 0:
        errors.append("audit_django_admin_surface_leftovers.py reported remaining left-behind admin surfaces")

    try:
        from scripts.sweep_django_admin_platformwide_layout import main as sweep_main
    except Exception:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "sweep_django_admin_platformwide_layout",
            ROOT / "scripts" / "sweep_django_admin_platformwide_layout.py",
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        sweep_main = mod.main
    if sweep_main() != 0:
        errors.append("sweep_django_admin_platformwide_layout.py reported remaining layout landmines")

    try:
        from scripts.audit_django_admin_miss_nothing import main as miss_nothing_main
    except Exception:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "audit_django_admin_miss_nothing",
            ROOT / "scripts" / "audit_django_admin_miss_nothing.py",
        )
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        miss_nothing_main = mod.main
    if miss_nothing_main() != 0:
        errors.append("audit_django_admin_miss_nothing.py reported remaining Django surface defects")

    quickaction = _read("static/js/_pages/admin-quickaction.js")
    if 'data-rmc-django-workspace="change-form"' not in quickaction:
        errors.append("admin-quickaction.js must refuse floating FAB on intelligent change-form canvas")

    country = _read("templates/admin/registries/countryregistry/change_form.html")
    if "{{ block.super }}" in country and "rmc-mv-form-with-preview" in country:
        errors.append("countryregistry change_form must not wrap shared canvas content in a nested preview grid")
    if 'data-rmc-mv-preview-drawer' not in country:
        errors.append("countryregistry preview must use drawer/popout affordance")

    app_index = _read("templates/admin/app_index.html")
    if 'data-rmc-django-command-band="app-index"' not in app_index:
        errors.append("templates/admin/app_index.html missing app-index command band")
    if "admin_app_index_rail.html" not in app_index:
        errors.append("templates/admin/app_index.html must include page-aware app-index rail")
    if 'data-rmc-django-workspace="app-index"' not in app_index:
        errors.append("templates/admin/app_index.html missing app-index workspace marker")

    app_rail = _read("templates/admin/includes/admin_app_index_rail.html")
    if "admin_page_aware_rail" not in app_rail or 'data-rmc-django-rail-page-aware="1"' not in app_rail:
        errors.append("admin_app_index_rail.html must be page-aware")

    for guided_path in (
        "templates/admin/schools/school/delete_guided.html",
        "templates/admin/schools/school/waive_subscription_form.html",
    ):
        guided = _read(guided_path)
        if "admin_guided_surface_rail.html" not in guided:
            errors.append(f"{guided_path} must include guided page-aware rail")
        if 'data-rmc-django-workspace="guided"' not in guided:
            errors.append(f"{guided_path} must use guided django workspace canvas")
        if "rmc-django-form-panel" not in guided:
            errors.append(f"{guided_path} must use premium form panel frame")

    if "admin_page_aware_rail" not in _read("templates/admin/includes/admin_index_context_rail.html"):
        errors.append("admin_index_context_rail.html must include page-aware rail")

    return errors


def _audit_admin_template_overrides() -> list[str]:
    errors: list[str] = []
    admin_templates = ROOT / "templates" / "admin"
    safe_extends = (
        'extends "admin/change_form.html"',
        "extends 'admin/change_form.html'",
        'extends "admin/change_list.html"',
        "extends 'admin/change_list.html'",
        'extends "admin/base_site.html"',
        "extends 'admin/base_site.html'",
        'extends "admin/base.html"',
        "extends 'admin/base.html'",
        'extends "admin/app_index.html"',
        "extends 'admin/app_index.html'",
    )
    for path in admin_templates.rglob("*.html"):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if rel in {
            "templates/admin/base.html",
            "templates/admin/base_site.html",
            "templates/admin/change_form.html",
            "templates/admin/change_list.html",
        }:
            continue
        if rel.endswith(("change_form.html", "change_list.html", "app_index.html", "index.html")):
            if "{% extends" in text and not any(token in text for token in safe_extends):
                errors.append(f"{rel}: admin override does not inherit a shared admin canvas template")
            if "{% extends" not in text and "<html" in text.lower():
                errors.append(f"{rel}: standalone admin HTML bypasses the shared admin canvas")

    admin_py = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (ROOT / "apps").rglob("admin.py"))
    template_refs = set(re.findall(r"change_(?:form|list)_template\s*=\s*[\"']([^\"']+)[\"']", admin_py))
    for ref in sorted(template_refs):
        path = ROOT / "templates" / ref
        if not path.is_file():
            errors.append(f"{ref}: referenced admin template is missing")
            continue
        text = path.read_text(encoding="utf-8")
        if "{% extends" in text and not any(token in text for token in safe_extends):
            errors.append(f"{ref}: referenced admin template bypasses shared change_form/change_list/base")
        if "{% extends" not in text and "<html" in text.lower():
            errors.append(f"{ref}: referenced admin template is standalone HTML")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())
