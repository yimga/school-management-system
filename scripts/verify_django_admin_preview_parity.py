#!/usr/bin/env python3
"""Gate live Django admin CSS/templates against approved design-preview HTML.

Single lock file (do not invent versions in consumers):
  var/admin-approval-build-lock.json

Approval sources of truth (do not invent ratios):
  var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html
  var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html

PASS when live shell carries the same workspace grid + table.fill contract
AND every consumer (templates, CSS cache-bust, SW, auditors) matches the lock.

Wired into: architectural-boundaries.yml, pre_push_boundary_check,
render_predeploy.sh, verify_ci_gate_wiring REQUIRED_GATES.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "var/admin-approval-build-lock.json"

OPERATOR_PREVIEW = (
    ROOT
    / "var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html"
)
TENANT_PREVIEW = (
    ROOT / "var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html"
)
CANVAS_CSS = ROOT / "static/css/rmc-admin-approval-surface-v15.css"
BASE_SITE = ROOT / "templates/admin/base_site.html"
BASE = ROOT / "templates/admin/base.html"
NAV_BRIDGE = ROOT / "templates/components/admin_nav_bridge.html"
SUBMIT_LINE = ROOT / "templates/admin/submit_line.html"
INDEX_TENANT = ROOT / "templates/admin/index_tenant.html"
INDEX_OPERATOR = ROOT / "templates/admin/index_superadmin.html"
CHANGE_FORM = ROOT / "templates/admin/change_form.html"
CHANGE_LIST = ROOT / "templates/admin/change_list.html"
SW = ROOT / "static/js/service-worker.js"
SW_BASELINE = ROOT / "var/security-audit-baseline-service-worker-version.json"
MISS_NOTHING = ROOT / "scripts/audit_django_admin_miss_nothing.py"
PLATFORM_SWEEP = ROOT / "scripts/sweep_django_admin_platformwide_layout.py"
CANVAS_AUDIT = ROOT / "scripts/audit_django_admin_canvas_contract.py"

_WS_GRID_RE = re.compile(
    r"\.ws\s*\{[^}]*grid-template-columns\s*:\s*([^;}]+)",
    re.I | re.S,
)
_NORMALIZE = re.compile(r"\s+")
_SW_RE = re.compile(r'const\s+CACHE_VERSION\s*=\s*"([^"]+)"')


def _norm(s: str) -> str:
    return _NORMALIZE.sub("", s.strip().lower())


def _extract_ws_grid(preview: Path) -> str:
    text = preview.read_text(encoding="utf-8")
    m = _WS_GRID_RE.search(text)
    if not m:
        raise SystemExit(f"PREVIEW_PARITY_FAIL: no .ws grid-template-columns in {preview}")
    return _norm(m.group(1))


def _load_lock() -> dict:
    if not LOCK_PATH.is_file():
        raise SystemExit(f"PREVIEW_PARITY_FAIL: missing lock {LOCK_PATH}")
    return json.loads(LOCK_PATH.read_text(encoding="utf-8"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    errors: list[str] = []
    lock = _load_lock()
    build_id = str(lock.get("build_id") or "")
    cache_bust = str(lock.get("cache_bust") or "")
    sw_version = str(lock.get("sw_version") or "")
    seal = str(lock.get("seal") or "2026-07-20-preview-parity-sot")
    visible_proofs = list(lock.get("visible_proofs") or [])

    if not build_id or not cache_bust or not sw_version:
        errors.append("admin-approval-build-lock.json missing build_id/cache_bust/sw_version")

    if not OPERATOR_PREVIEW.is_file():
        errors.append(f"missing operator approval preview: {OPERATOR_PREVIEW}")
    if not TENANT_PREVIEW.is_file():
        errors.append(f"missing tenant approval preview: {TENANT_PREVIEW}")
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print("PREVIEW_PARITY_FAIL")
        return 1

    op_grid = _extract_ws_grid(OPERATOR_PREVIEW)
    ten_grid = _extract_ws_grid(TENANT_PREVIEW)

    if op_grid != _norm("minmax(0,1fr) minmax(9.2rem,17%) 2.35rem"):
        errors.append(f"operator preview .ws grid drifted: {op_grid}")
    if ten_grid != _norm("minmax(0,1fr) minmax(9.5rem,18%) 2.35rem"):
        errors.append(f"tenant preview .ws grid drifted: {ten_grid}")

    css = _read(CANVAS_CSS)
    base_site = _read(BASE_SITE)
    base = _read(BASE)
    nav = _read(NAV_BRIDGE)
    submit = _read(SUBMIT_LINE)
    index_t = _read(INDEX_TENANT)
    index_op = _read(INDEX_OPERATOR)
    change_form = _read(CHANGE_FORM)
    change_list = _read(CHANGE_LIST)
    sw = _read(SW)
    sw_base = _read(SW_BASELINE)
    miss = _read(MISS_NOTHING)
    sweep = _read(PLATFORM_SWEEP)
    canvas_audit = _read(CANVAS_AUDIT)

    if seal not in css:
        errors.append(f"canvas CSS missing terminal seal {seal}")

    css_n = _norm(css)
    if "minmax(0,1fr)minmax(9.2rem,17%)2.35rem" not in css_n:
        errors.append(
            "live CSS missing operator approval grid "
            "minmax(0,1fr) minmax(9.2rem,17%) 2.35rem"
        )
    if "minmax(0,1fr)minmax(9.5rem,18%)2.35rem" not in css_n:
        errors.append(
            "live CSS missing tenant approval grid "
            "minmax(0,1fr) minmax(9.5rem,18%) 2.35rem"
        )

    seal_idx = css.find(seal)
    if seal_idx >= 0:
        seal_tail = css[seal_idx:]
        if "table-layout: fixed" not in seal_tail and "table-layout:fixed" not in seal_tail:
            errors.append(f"{seal} must set table-layout: fixed (preview table.fill)")
        if re.search(r"minmax\(\s*15rem\s*,\s*min\(\s*22vw", seal_tail):
            errors.append(f"{seal} must not reintroduce minmax(15rem, min(22vw…)) wide rail")

    # --- Lock sync: every consumer must match the build lock ---
    if f"?v={cache_bust}" not in base_site:
        errors.append(f"base_site cache-bust must be ?v={cache_bust} (lock)")
    if f"?v={cache_bust}" not in canvas_audit and cache_bust not in canvas_audit:
        errors.append(f"audit_django_admin_canvas_contract.py must expect {cache_bust}")
    if f'EXPECTED_CACHE_BUST = "{cache_bust}"' not in miss:
        errors.append(f"audit_django_admin_miss_nothing.py EXPECTED_CACHE_BUST must be {cache_bust}")
    if f'EXPECTED_CACHE_BUST = "{cache_bust}"' not in sweep:
        errors.append(
            f"sweep_django_admin_platformwide_layout.py EXPECTED_CACHE_BUST must be {cache_bust}"
        )
    if f'EXPECTED_SW = "{sw_version}"' not in miss:
        errors.append(f"audit_django_admin_miss_nothing.py EXPECTED_SW must be {sw_version}")
    if f'EXPECTED_SW = "{sw_version}"' not in sweep:
        errors.append(
            f"sweep_django_admin_platformwide_layout.py EXPECTED_SW must be {sw_version}"
        )

    sw_m = _SW_RE.search(sw)
    if not sw_m or sw_m.group(1) != sw_version:
        errors.append(
            f"service-worker CACHE_VERSION must be {sw_version} (got "
            f"{sw_m.group(1) if sw_m else 'missing'})"
        )
    if f'"raw": "{sw_version}"' not in sw_base and sw_version not in sw_base:
        errors.append(f"SW baseline JSON must record raw={sw_version}")

    build_attr = f'data-rmc-admin-approval-build="{build_id}"'
    if build_attr not in base:
        errors.append(f"admin/base.html must emit {build_attr}")
    if build_attr not in base_site and f'content="{build_id}"' not in base_site:
        errors.append(f"base_site must emit approval build meta/attr for {build_id}")

    # BOTH hosts must show the visible deploy-proof chip (operator + tenant /admin/).
    chip_needle = "rmc-admin-approval-build-chip"
    if chip_needle not in index_t or build_id not in index_t:
        errors.append(
            f"tenant index_tenant.html must show visible approval chip for {build_id}"
        )
    if chip_needle not in index_op or build_id not in index_op:
        errors.append(
            f"operator index_superadmin.html must show visible approval chip for {build_id}"
        )
    if 'data-rmc-admin-index-canvas="operator"' not in index_op and 'data-rmc-admin-discover="1"' not in index_op:
        errors.append("index_superadmin.html must use discover canvas (operator)")
    if 'data-rmc-admin-index-canvas="tenant"' not in index_t and 'data-rmc-admin-discover="1"' not in index_t:
        errors.append("index_tenant.html must use discover canvas (tenant)")
    # Discover, Scan, and Edit all use the approved page-aware inner grid.
    if 'data-rmc-admin-archetype="discover"' not in index_op or 'data-rmc-admin-archetype="discover"' not in index_t:
        errors.append("operator + tenant indexes must set data-rmc-admin-archetype=discover")
    if "cp-steering" in index_op:
        errors.append("operator index must not render cp-steering fluff banner")
    if "admin_v1_index_surface_previews.html" not in index_op:
        errors.append("operator index must restore live surface sections (tags/changelist/changeform)")
    if "admin_index_context_rail.html" not in index_op or "admin_index_context_rail.html" not in index_t:
        errors.append("operator + tenant indexes must include their page-aware context rail")
    if "admin_workspace_tools.html" not in index_op or "admin_workspace_tools.html" not in index_t:
        errors.append("operator + tenant indexes must include page-aware workspace tools")
    if "admin_workspace_metrics_strip.html" in change_form or "admin_workspace_metrics_strip.html" in change_list:
        errors.append("change_form/change_list must not include metrics strip (v15 zero fluff)")
    if "rmc-django-view-toggle" in change_form or "admin_change_form_mode_panels.html" in change_form:
        errors.append("change_form must not ship Form/Audit toggle chrome (v15)")
    if 'data-rmc-admin-archetype="edit"' not in change_form:
        errors.append("change_form must set data-rmc-admin-archetype=edit")
    if 'data-rmc-admin-archetype="scan"' not in change_list:
        errors.append("change_list must set data-rmc-admin-archetype=scan")
    if "rmc_info_tag" not in change_form or "rmc_info_tag" not in change_list:
        errors.append("change_form/change_list must educate via rmc_info_tag, not manifesto ledes")
    if "admin_workspace_tools.html" not in change_form or "admin_workspace_tools.html" not in change_list:
        errors.append("change_form/change_list must include workspace tools (preview col-3)")

    for proof in visible_proofs:
        haystacks = (base_site, base, index_t, index_op, nav, css)
        if not any(proof in h for h in haystacks):
            errors.append(f"visible proof missing from live shell: {proof!r}")

    if 'id="rmc-admin-preview-parity-critical"' not in base_site:
        errors.append("base_site must ship the critical Admin OS layout <style> with HTML")
    if re.search(
        r'<style[^>]*id="rmc-admin-preview-parity-critical"[^>]*media="not all"',
        base_site,
    ) or re.search(
        r'<style[^>]*media="not all"[^>]*id="rmc-admin-preview-parity-critical"',
        base_site,
    ):
        errors.append(
            "base_site must NOT disable critical Admin OS layout CSS (media=not all left v15.2 unpainted)"
        )
    if 'data-rmc-layout-owner="approval-v15-critical"' not in base_site:
        errors.append("critical inline style must declare data-rmc-layout-owner=approval-v15-critical")
    if '[data-rmc-admin-archetype="discover"]' not in base_site:
        errors.append("critical inline CSS must include Discover canvas ownership")
    if '[data-rmc-admin-index-canvas="operator"][data-rmc-admin-discover="1"]' not in base_site:
        errors.append(
            "critical inline CSS must own the Discover operator canvas "
            "(operator Catalog right-gutter fix)"
        )
    if '[data-rmc-admin-index-canvas="operator"][data-rmc-admin-discover="1"]' not in css:
        errors.append("v15 CSS must own the Discover operator canvas")
    # Discover must not share the Edit/Scan 3-col selector list
    if re.search(
        r"\[data-rmc-admin-index-canvas=\"operator\"\]\s*,\s*\n?\s*\[data-rmc-django-workspace=\"change-list\"\]",
        css,
    ):
        errors.append(
            "v15 must not put Discover index-canvas on the Edit/Scan 3-col workbench rule "
            "(empty rail|tools = right gutter)"
        )
    if base_site.count("rmc-admin-approval-surface-v15.css") != 1:
        errors.append("base_site must load exactly one v15 approval layout owner")
    if base_site.rfind("rmc-admin-approval-surface-v15.css") < base_site.rfind("admin-brand-resolved-tokens"):
        errors.append("v15 approval layout owner must be last-loaded after resolved theme tokens")

    if "rmc-django-save-compact" not in submit:
        errors.append("submit_line.html must implement compact Save (preview save-compact)")
    if 'data-rmc-admin-archetype="discover"' not in index_t or "This school only" not in index_t:
        errors.append("index_tenant.html must be Discover archetype with This school only host voice")
    if 'data-rmc-django-workspace="change-form"' not in change_form:
        errors.append("change_form.html missing data-rmc-django-workspace=change-form")
    if 'data-rmc-django-workspace="change-list"' not in change_list:
        errors.append("change_list.html missing data-rmc-django-workspace=change-list")
    if base_site.count("rmc-admin-django-canvas-contract.css") != 1:
        errors.append("base_site must load the canonical Django canvas contract exactly once")
    if base_site.count("rmc_theme_experience_dual_plane_styles.html") != 1:
        errors.append("base_site must load theme-experience styles exactly once")
    if base_site.count("admin-nav-bridge-tenant.css") != 1:
        errors.append("base_site must own the tenant nav stylesheet exactly once in <head>")
    if base_site.count("rmc-tour.css") != 1:
        errors.append("base_site must own tour styles exactly once in <head>")
    if "rmc_tour_css_in_head=True" not in base_site:
        errors.append("body tour runtime must suppress its already-loaded head style")
    if "portal_row_detail_drawer_bundle.html" in base_site or "rmc-portal-row-detail-drawer.css" in base_site:
        errors.append("Django admin must not mount the global row-detail fixed overlay")
    if re.search(r"<link\b[^>]*\bstylesheet\b", nav, re.I):
        errors.append("admin_nav_bridge must not inject a stylesheet from inside <body>")
    if "cp_context_drawer_shell.html" in base_site:
        errors.append("Django admin must not render the fixed legacy Context overlay")
    if "_ai_copilot_rail.html" in base or "_operator_notebook.html" in base:
        errors.append("Django admin must not render a second global copilot/notebook tools rail")
    if "rmc_operator_footer_civic.html" in base or "admin-manager-sticky-slot" in base:
        errors.append("Django admin must not overlay the workbench with a fixed civic footer or empty sticky slot")
    if "admin_operator_steering_strip.html" in base or "rmc_operator_surface_strip" in base:
        errors.append("Django admin must not stack a global steering strip above its page command band")
    if "admin_change_form_header.html" in change_form or "admin_changelist_header.html" in change_list:
        errors.append("change form/list must not stack legacy secondary headers above the workspace")
    if "data-rmc-admin-preview-url" in change_form:
        errors.append("shared change form must not advertise a staged generic preview URL")
    if "--rmc-admin-v12-operator-rail: minmax(9.2rem, 17%)" not in css:
        errors.append("approval CSS must seal operator host rail identity")
    if "--rmc-admin-v12-tenant-rail: minmax(9.5rem, 18%)" not in css:
        errors.append("approval CSS must seal tenant host rail identity")
    if "@media (max-width: 1024px)" not in css:
        errors.append("approval CSS must seal tablet/mobile workspaces to one track at 1024px")
    if "position: static !important" not in css:
        errors.append("approval CSS must keep page rails, tools and save actions in document flow")
    if "--rmc-admin-v13-transfer-h" not in css:
        errors.append("approval CSS must height-cap .selector transfer lists (--rmc-admin-v13-transfer-h)")
    if "rmc-admin-transfer-panel" not in css:
        errors.append("approval CSS must style numbered collapsible transfer panels")
    if "v13 TERMINAL SEALS" not in css:
        errors.append("approval CSS must include terminal #cp-main-content cascade seals")
    if "v15 ARCHETYPES" not in css:
        errors.append("approval CSS must include v15 ARCHETYPES geometry rules")
    if "max-w-2xl" not in css or "max-width: none !important" not in css:
        errors.append("approval CSS must neutralize Unfold max-w-2xl left-void on form controls")
    workspace_js = _read(ROOT / "static/js/rmc-admin-workspace.js")
    if "initTransferCondensation" not in workspace_js or "rmc-admin-transfer-panel" not in workspace_js:
        errors.append("rmc-admin-workspace.js must condense M2M selectors into transfer panels")
    if "TRANSFER_SIZE" not in workspace_js:
        errors.append("rmc-admin-workspace.js must clamp selector size= attributes")
    app_index = _read(ROOT / "templates/admin/app_index.html")
    if app_index.count("data-rmc-admin-index-canvas=") != 1:
        errors.append("app_index must render one canvas; a nested duplicate recreates the right void")
    if change_form.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("change_form must expose one auditable primary fill panel")
    if change_list.count('data-rmc-django-primary-panel="1"') != 1:
        errors.append("change_list must expose one auditable primary fill panel")

    banned = [
        ("minmax(15rem, min(22vw", "wide 22vw rail (pre-approval)"),
        ("minmax(15rem, 18vw)", "2-col 18vw rail (stranded TOOLS)"),
        ("minmax(14rem, var(--rmc-admin-canvas-rail", "14rem canvas-rail (pre-approval)"),
        ("minmax(15rem, 18rem) 3rem", "15rem/18rem/3rem (pre-approval tools)"),
        ("table-layout: auto !important", "table-layout:auto invents right void"),
    ]
    for needle, reason in banned:
        if needle in css:
            errors.append(f"live canvas CSS still contains banned {reason}: {needle}")

    workspace_10x = _read(ROOT / "static/css/rmc-admin-workspace-10x.css")
    if "clamp(260px, 20vw, 330px)" in workspace_10x:
        errors.append("workspace-10x still forces 2-col clamp(260px…) — approval is 3-col")
    if "minmax(9.2rem, 17%)" not in workspace_10x and "minmax(9.2rem,17%)" not in workspace_10x:
        errors.append("workspace-10x must use operator approval grid minmax(9.2rem, 17%)")

    if seal not in css:
        errors.append(f"canvas CSS missing terminal ownership seal {seal}")
    seal_and_after = css[css.find(seal) :] if seal in css else ""
    if "#cp-main-content" not in seal_and_after:
        errors.append(f"{seal} (or later) must include #cp-main-content specificity override")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print("PREVIEW_PARITY_FAIL")
        return 1

    print("PREVIEW_PARITY_PASS")
    print(f"  operator .ws = {op_grid}")
    print(f"  tenant   .ws = {ten_grid}")
    print(f"  seal     = {seal}")
    print(f"  build    = {build_id}")
    print(f"  cache    = {cache_bust}")
    print(f"  sw       = {sw_version}")
    print(f"  lock     = {LOCK_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
