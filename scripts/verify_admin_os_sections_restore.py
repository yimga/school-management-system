#!/usr/bin/env python3
"""Seal Admin OS v15.4 section restore — fail if operator/tenant index sections regress."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    op = (ROOT / "templates/admin/index_superadmin.html").read_text(encoding="utf-8")
    ten = (ROOT / "templates/admin/index_tenant.html").read_text(encoding="utf-8")
    prev = (ROOT / "templates/admin/partials/admin_v1_index_surface_previews.html").read_text(
        encoding="utf-8"
    )
    cf = (ROOT / "templates/admin/change_form.html").read_text(encoding="utf-8")
    cl = (ROOT / "templates/admin/change_list.html").read_text(encoding="utf-8")
    bs = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
    nav = (ROOT / "apps/portal/help_section_nav.py").read_text(encoding="utf-8")
    admin_py = (ROOT / "config/admin.py").read_text(encoding="utf-8")
    css = (ROOT / "static/css/rmc-admin-approval-surface-v15.css").read_text(encoding="utf-8")
    lock = json.loads((ROOT / "var/admin-approval-build-lock.json").read_text(encoding="utf-8"))

    def must(cond: bool, msg: str) -> None:
        if not cond:
            errors.append(msg)

    # Operator restores
    must("admin_v1_index_surface_previews.html" in op, "operator index missing surface previews include")
    must("rmc-admin-section-jumps" in op, "operator index missing horizontal section jumps")
    must("rmc-admin-sec-catalog" in op, "operator index missing catalog section id")
    must('data-rmc-admin-archetype="discover"' in op, "operator index missing discover archetype")
    must("schools_school_add" in op, "operator index missing New school CTA")
    must("data-rmc-admin-pins" in op, "operator index missing pins row")
    must("rmc-admin-v1-200x.js" in bs, "base_site must load surface-preview interactivity JS")
    must("rmc-admin-v1-200x.css" in bs, "base_site must load surface-preview CSS")

    for sid in (
        "rmc-admin-sec-tags",
        "rmc-admin-sec-changelist",
        "rmc-admin-sec-changeform",
    ):
        must(f'id="{sid}"' in prev, f"surface preview partial missing #{sid}")
        must(sid in nav, f"admin_catalog_section_nav_items missing {sid}")

    must("rmc-admin-sec-hero" not in nav, "nav still points at removed hero section")
    must("rmc-admin-sec-catalog" in nav, "nav missing catalog anchor")

    # Tenant restores
    must("feature_control_panel" in ten, "tenant index missing Feature control CTA")
    must("Browse models" in ten, "tenant index missing Browse models jump")
    must("console_domains_hub" in ten, "tenant index missing Config center")
    must("rmc-admin-section-jumps" in ten, "tenant index missing catalog section jumps")
    must("rmc-tenant-admin-sec-catalog" in ten, "tenant index missing catalog section")
    must('data-rmc-admin-archetype="discover"' in ten, "tenant index missing discover archetype")

    # Legacy fluff stays out; approved page-aware rail/tools stay present.
    for label, text in (("operator", op), ("tenant", ten)):
        must("cp-steering" not in text, f"{label} index reintroduced cp-steering")
        must("cp-kpi-strip" not in text, f"{label} index reintroduced KPI strip")
        must("admin_workspace_tools.html" in text, f"{label} index missing approved tools strip")
        must("admin_index_context_rail.html" in text, f"{label} index missing page-aware context rail")
        must('class="rmc-section-nav"' not in text and "class='rmc-section-nav'" not in text,
             f"{label} index must use rmc-admin-section-jumps (not sticky .rmc-section-nav)")

    # Edit/Scan rails intact
    must("admin_change_form_rail.html" in cf, "change_form missing page-aware rail")
    must("admin_workspace_tools.html" in cf, "change_form missing tools")
    must('data-rmc-admin-archetype="edit"' in cf, "change_form missing edit archetype")
    must("admin_workspace_metrics_strip.html" not in cf, "change_form reintroduced metrics strip")
    must("admin_changelist_rail.html" in cl, "change_list missing page-aware rail")
    must('data-rmc-admin-archetype="scan"' in cl, "change_list missing scan archetype")

    # Layout owner / context
    crit = bs.split('id="rmc-admin-preview-parity-critical"', 1)
    must(len(crit) == 2, "critical layout style missing")
    if len(crit) == 2:
        head = crit[1].split(">", 1)[0]
        must('media="not all"' not in head, "critical layout CSS disabled with media=not all")
    must("approval-v15-critical" in bs, "critical layout owner marker missing")
    must("rmc-admin-approval-surface-v15.css" in bs, "v15 CSS owner missing")
    must("rmc-admin-os-innovations.js" in bs, "innovations JS missing")
    must("build_admin_index_surface_context" in admin_py, "PlatformAdmin must build surface context")
    must("admin_catalog_section_nav_items" in admin_py, "PlatformAdmin must build section nav")
    must(".rmc-admin-section-jumps" in css, "v15 CSS missing section-jumps rules")

    build = lock.get("build_id") or ""
    must(build in op and build in ten, f"indexes must show lock build_id {build}")
    must("admin_v1_index_surface_previews.html" in (lock.get("visible_proofs") or []),
         "lock visible_proofs must require surface previews")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print("ADMIN_OS_SECTIONS_RESTORE_FAIL")
        return 1
    print("ADMIN_OS_SECTIONS_RESTORE_PASS")
    print(f"  build={build} cache={lock.get('cache_bust')} proofs={len(lock.get('visible_proofs') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
