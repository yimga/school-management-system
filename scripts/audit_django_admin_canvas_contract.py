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

    if not css_path.is_file():
        errors.append("static/css/rmc-admin-django-canvas-contract.css is missing")
        css = ""
    else:
        css = css_path.read_text(encoding="utf-8")

    contract_link = "rmc-admin-django-canvas-contract.css"
    if contract_link not in base_site:
        errors.append("templates/admin/base_site.html does not load the final Django canvas contract")
    if "?v=20260717-parity-close" not in base_site:
        errors.append("Django canvas contract link must use the parity-close cache bust for deployment visibility")
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
    if "parity-close" not in css:
        errors.append("rmc-admin-django-canvas-contract.css must include parity-close G3-G9 block")
    if "rmc-django-preview-card" not in css:
        errors.append("canvas contract must style .rmc-django-preview-card preview stage")
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
    if 'data-rmc-django-view-toggle="1"' not in change_form:
        errors.append("admin/change_form.html missing Form/Preview/Audit view toggle")
    if 'data-rmc-django-view-mode="form"' not in change_form:
        errors.append("admin/change_form.html missing default view-mode marker")
    if "admin_change_form_mode_panels.html" not in change_form:
        errors.append("admin/change_form.html must include Preview/Audit mode panels")
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
    if "admin_preview_card_stage.html" not in change_form and "admin_change_form_mode_panels.html" in change_form:
        mode_panels = _read("templates/admin/includes/admin_change_form_mode_panels.html")
        if "admin_preview_card_stage.html" not in mode_panels:
            errors.append("admin change-form preview mode must include admin_preview_card_stage.html")
    mode_panels = _read("templates/admin/includes/admin_change_form_mode_panels.html")
    if "admin_preview_card_stage.html" not in mode_panels:
        errors.append("admin_change_form_mode_panels.html must include preview-card stage")
    rail = _read("templates/admin/includes/admin_change_form_rail.html")
    if "admin_preview_card_stage.html" not in rail:
        errors.append("admin_change_form_rail.html must include preview-card stage")
    if "admin_workspace_metrics_strip.html" not in change_form:
        errors.append("admin/change_form.html must include workspace metrics strip")
    if "admin_workspace_tools.html" not in change_form:
        errors.append("admin/change_form.html must include 48px workspace tools")
    if "admin_workspace_metrics_strip.html" not in change_list:
        errors.append("admin/change_list.html must include workspace metrics strip")
    if "admin_workspace_tools.html" not in change_list:
        errors.append("admin/change_list.html must include 48px workspace tools")
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
    if "mountPreviewStageInDrawer" not in workspace_js:
        errors.append("rmc-admin-workspace.js must mount preview-card stage into drawer")

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
    workspace_js = _read("static/js/rmc-admin-workspace.js")
    if "data-rmc-django-view-mode" not in workspace_js or "setViewMode" not in workspace_js:
        errors.append("rmc-admin-workspace.js must wire Form/Preview/Audit view mode")

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
        "rmc-django-preview-card",
        "data-rmc-django-tools",
        "data-rmc-django-metrics",
        "data-rmc-django-table-pagination",
        '[data-rmc-admin-index-canvas="operator"]',
        "rmc-tenant-admin-page-body",
        "container-type: inline-size",
        "Final platform-wide/tenant-wide Django sweep",
        "Structural canvas closure, 2026-07-11",
        "Production hardening, 2026-07-12",
        "Preview parity closure, 2026-07-12",
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
        'data-rmc-admin-index-canvas="tenant"',
        "rmc-admin-catalog-index",
        "Tenant model catalog",
        "admin_catalog",
    ):
        if token not in tenant_index:
            errors.append(f"templates/admin/index_tenant.html missing intelligent index token: {token}")

    if "Raw model CRUD only" in tenant_index:
        errors.append("templates/admin/index_tenant.html must not use the empty Raw model CRUD-only hero")

    if "def index(self, request, extra_context=None):" not in admin_py:
        errors.append("config/admin.py TenantAdminSite must override index for catalog context")
    if "build_platform_admin_catalog" not in admin_py:
        errors.append("config/admin.py must build admin_catalog for tenant index")
    # TenantAdminSite.index must call build_platform_admin_catalog (not only PlatformAdminSite)
    tenant_site_slice = admin_py.split("class TenantAdminSite", 1)[-1].split("class PlatformAdminSite", 1)[0]
    if "build_platform_admin_catalog" not in tenant_site_slice:
        errors.append("TenantAdminSite.index must build admin_catalog via build_platform_admin_catalog")

    if 'url_name|default:"" != "index"' not in nav_bridge and "!= \"index\"" not in nav_bridge:
        errors.append("admin_nav_bridge must skip operator_console_strip on admin index")
    if "operator_console_strip" not in nav_bridge:
        errors.append("admin_nav_bridge must still expose operator_console_strip on non-index pages")

    if 'data-rmc-admin-catalog-index="1"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html missing catalog index marker")
    if 'data-rmc-django-command-band="admin-index"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html missing admin-index command band")
    if 'data-rmc-admin-index-canvas="operator"' not in operator_index:
        errors.append("templates/admin/index_superadmin.html missing operator index canvas wrapper")
    if "admin_index_context_rail.html" not in operator_index:
        errors.append("templates/admin/index_superadmin.html must include shared index context rail")
    if "admin_index_context_rail.html" not in tenant_index:
        errors.append("templates/admin/index_tenant.html must include shared index context rail")

    base = _read("templates/admin/base.html")
    if 'url_name|default:"" != "index"' not in base or "tenant_admin_decision_banner" not in base:
        errors.append("admin/base.html must skip tenant decision banner on admin index")

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
