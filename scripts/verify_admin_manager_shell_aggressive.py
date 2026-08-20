#!/usr/bin/env python3
"""
Aggressive gate bundle for manager /admin/ + control-plane shell parity (v3.62.17+).
Exits 0 with ADMIN_MANAGER_SHELL_AGGRESSIVE_PASS on full pass.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], label: str) -> list[str]:
    import os

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        snippet = "\n".join(out.strip().splitlines()[-12:])
        return [f"{label}: exit {proc.returncode}\n{snippet}"]
    return []


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--css-only",
        action="store_true",
        help="Fast path: shell parity + layout only (preview shell 100x phase 2)",
    )
    args = parser.parse_args()

    errors: list[str] = []
    py = sys.executable

    checks: list[tuple[str, list[str]]] = [
        ("preview_shell_impl", [py, "scripts/verify_all_preview_shell_html_implementation.py"]),
        ("shell_preview_parity", [py, "scripts/verify_platform_shell_preview_parity.py"]),
        ("manager_admin_layout", [py, "scripts/verify_manager_admin_cp_layout.py"]),
        ("django_admin_canvas_contract", [py, "scripts/audit_django_admin_canvas_contract.py"]),
        ("tenant_sidebar", [py, "scripts/verify_tenant_admin_sidebar_v2.py"]),
        ("operator_sidebar", [py, "scripts/verify_operator_admin_sidebar_v2.py"]),
    ]
    if not args.css_only:
        checks.extend(
            [
                ("interaction_integrity", [py, "scripts/verify_interaction_integrity_completion.py"]),
                ("dead_hrefs", [py, "scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
                ("page_fold", [py, "scripts/verify_page_fold_standards.py"]),
                ("template_safety", [py, "scripts/audit_template_render_safety.py"]),
                ("admin_gear_up", [py, "scripts/verify_admin_platform_gear_up_bundle.py"]),
                (
                    "admin_changelist",
                    [
                        py,
                        "scripts/verify_admin_changelist_render_contract.py",
                    ],
                ),
                ("admin_steering", [py, "scripts/verify_admin_steering_strip_contract.py"]),
                ("admin_templates", [py, "scripts/verify_django_admin_canvas_templates_compile.py"]),
                ("admin_miss_nothing", [py, "scripts/audit_django_admin_miss_nothing.py"]),
            ]
        )

    for label, cmd in checks:
        errors.extend(_run(cmd, label))

    index = (ROOT / "templates/admin/index_superadmin.html").read_text(encoding="utf-8")
    for needle in (
        "rmc-page-fold-nav",
        "data-rmc-section-anchor",
        'class="rmc-admin-catalog-section ',
        "data-rmc-admin-catalog-section",
        "admin_v1_index_surface_previews",
    ):
        if needle not in index:
            errors.append(f"index_superadmin.html: missing {needle}")

    help_drawer = (ROOT / "templates/partials/help_contextual_drawer.html").read_text(encoding="utf-8")
    if "rmc-help-contextual-drawer" not in help_drawer or "Need help on this page?" not in help_drawer:
        errors.append("help_contextual_drawer.html: contextual help chip missing")

    skeleton = (ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if "help_contextual_drawer.html" not in skeleton:
        errors.append("control_plane_skeleton.html: contextual help drawer missing")
    if "rmc-footer-notebook-anchor" in skeleton:
        errors.append(
            "control_plane_skeleton.html: footer notebook dock removed (use copilot rail ✎)"
        )
    if "_operator_notebook.html" not in skeleton:
        errors.append("control_plane_skeleton.html: operator notebook partial missing")
    if "_workspace_context.html" in skeleton:
        errors.append("control_plane_skeleton.html: workspace_context must not ship in sidebar")
    if "data-rmc-copilot-page-help" not in skeleton or "rmc-platform-vertical-compact.css" not in skeleton:
        errors.append("control_plane_skeleton.html: copilot page-help attr or vertical-compact CSS missing")

    admin_base = (ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
    if "_workspace_context.html" in admin_base:
        errors.append("admin/base.html: workspace_context must not ship in manager sidebar")
    if 'data-rmc-backoffice-frame="v2"' not in admin_base:
        errors.append("admin/base.html: missing backoffice frame v2 marker")
    if 'data-rmc-backoffice-scroll-root="main"' not in admin_base:
        errors.append("admin/base.html: missing backoffice main scroll-root marker")
    if 'data-rmc-backoffice-page-body="1"' not in admin_base:
        errors.append("admin/base.html: missing backoffice page body marker")
    if "control_plane_unified_header.html" not in admin_base:
        errors.append("admin/base.html: consolidated manager header include missing")
    if "_activity_ticker_drawer.html" not in admin_base:
        errors.append("admin/base.html: drawer-backed operator activity surface missing")
    if "_ai_copilot_rail.html" in admin_base:
        errors.append("admin/base.html: global copilot rail must not duplicate page-aware admin tools")

    admin_base_site = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
    if admin_base_site.count("rmc-admin-changelist-live.css") < 2:
        errors.append("admin/base_site.html: changelist live CSS must load for manager and tenant admin")
    if 'rmc-admin-changelist-live.css\' %}" media="print"' in admin_base_site:
        errors.append("admin/base_site.html: changelist live CSS must be a screen stylesheet, not lazy print/onload")
    if "rmc-admin-emergency-full-canvas-v17.css" not in admin_base_site:
        errors.append("admin/base_site.html: missing terminal v17 Django canvas owner")
    if 'data-rmc-admin-layout-owner="emergency-v17"' not in admin_base_site:
        errors.append("admin/base_site.html: terminal Django canvas owner is not explicit")

    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    if "_activity_ticker_inline.html" not in portal:
        errors.append("portal_base.html: manager bridge must retain drawer-backed inline activity")
    mgr_hdr = portal.find('data-rmc-shell-header="portal-manager"')
    if mgr_hdr >= 0:
        # The portal owns the header include while the inline badge marker lives
        # in that included topbar partial; audit the composed source contract.
        hdr_slice = (
            portal[mgr_hdr:]
            + (ROOT / "templates/partials/manager_operator_topbar.html").read_text(encoding="utf-8")
            + (ROOT / "templates/partials/cockpit/_activity_ticker_inline.html").read_text(encoding="utf-8")
        )
        strip_i = hdr_slice.find("data-rmc-cp-ticker-inline")
        nav_i = hdr_slice.find("cp-nav-row")
        if strip_i < 0:
            errors.append("portal_base.html: manager header missing inline activity badge")
        elif nav_i >= 0 and nav_i > strip_i:
            errors.append("portal_base.html: manager header must be utility → ticker → nav")

    cockpit_defaults = (ROOT / "apps/siteconfig/cockpit_manager_200x.py").read_text(encoding="utf-8")
    if '"enabled": True' not in cockpit_defaults.split("_manager_ai_copilot_defaults")[1].split("def _manager_world_map")[0]:
        errors.append("cockpit_manager_200x.py: ai_copilot_rail.enabled must default True")

    theme_tail = (ROOT / "templates/partials/rmc_authenticated_theme_tail.html").read_text(encoding="utf-8")
    if "{#" in theme_tail and "#}" in theme_tail:
        errors.append("rmc_authenticated_theme_tail.html: use {% comment %} not {# #} (bleed risk)")

    copilot_partial = (ROOT / "templates/partials/cockpit/_ai_copilot_rail.html").read_text(encoding="utf-8")
    if "data-rmc-page-help" not in copilot_partial:
        errors.append("_ai_copilot_rail.html: page-help control missing on rail")

    changelist_tpl = (ROOT / "templates/admin/change_list.html").read_text(encoding="utf-8")
    if "cp-changelist-live" not in changelist_tpl or "cp-changelist--preview" in changelist_tpl:
        errors.append("change_list.html: must use cp-changelist-live (not preview grid class)")
    if 'data-rmc-admin-table-contract="native-table-scroll"' not in changelist_tpl:
        errors.append("change_list.html: missing native table scroll contract marker")
    change_form_tpl = (ROOT / "templates/admin/change_form.html").read_text(encoding="utf-8")
    if 'data-rmc-admin-form-contract="premium-form-frame"' not in change_form_tpl:
        errors.append("change_form.html: missing premium form frame contract marker")
    submit_line_tpl = (ROOT / "templates/admin/submit_line.html").read_text(encoding="utf-8")
    if 'data-rmc-admin-submit-contract="sticky-safe-actions"' not in submit_line_tpl:
        errors.append("submit_line.html: missing sticky-safe action contract marker")
    preview_tpl = (ROOT / "templates/admin/partials/admin_v1_index_surface_previews.html").read_text(
        encoding="utf-8"
    )
    if "cp-changelist--preview" not in preview_tpl:
        errors.append("admin_v1_index_surface_previews.html: missing cp-changelist--preview scoping")

    v1_css = (ROOT / "static/css/rmc-admin-v1-200x.css").read_text(encoding="utf-8")
    if ".cp-changelist.cp-changelist--preview" not in v1_css:
        errors.append("rmc-admin-v1-200x.css: preview changelist grid must be scoped to --preview")
    if not (ROOT / "static/css/rmc-admin-changelist-live.css").is_file():
        errors.append("rmc-admin-changelist-live.css: missing live changelist stylesheet")
    else:
        live_css = (ROOT / "static/css/rmc-admin-changelist-live.css").read_text(encoding="utf-8")
        for token in (
            "overflow-x: auto",
            "display: table !important",
            "display: table-row !important",
            "display: table-cell !important",
            "white-space: nowrap",
            "admin-premium-shell",
        ):
            if token not in live_css:
                errors.append(f"rmc-admin-changelist-live.css: missing {token}")
    if not (ROOT / "static/css/rmc-admin-django-canvas-contract.css").is_file():
        errors.append("rmc-admin-django-canvas-contract.css: missing final Django canvas contract")
    if not (ROOT / "static/css/rmc-admin-emergency-full-canvas-v17.css").is_file():
        errors.append("rmc-admin-emergency-full-canvas-v17.css: missing terminal layout owner")
    parity_css = (ROOT / "static/css/admin-cp-parity.css").read_text(encoding="utf-8")
    for token in (
        "--rmc-backoffice-gutter",
        "--rmc-backoffice-form-max",
        "data-rmc-admin-form-contract=\"premium-form-frame\"",
        "data-rmc-admin-submit-contract=\"sticky-safe-actions\"",
        "#cp-main-content #content-main.cp-form-frame",
        ".cp-form-frame",
    ):
        if token not in parity_css:
            errors.append(f"admin-cp-parity.css: missing {token}")

    errors.extend(_run([py, "scripts/verify_theme_tail_no_bleed.py"], "theme_tail_no_bleed"))

    guard = (ROOT / "static/js/rmc-surface-overlay-guard.js").read_text(encoding="utf-8")
    if "MutationObserver" not in guard or 'getElementById("modal-overlay")' not in guard:
        errors.append("rmc-surface-overlay-guard.js: incomplete overlay guard")

    if errors:
        print("ADMIN_MANAGER_SHELL_AGGRESSIVE_FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("ADMIN_MANAGER_SHELL_AGGRESSIVE_PASS")
    print(f"  checks: {len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
