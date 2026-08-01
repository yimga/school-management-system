#!/usr/bin/env python3
"""Seal Admin OS empty-space / full-bleed contract (operator + tenant).

Fails when CSS/templates reintroduce:
  - Discover Catalog phantom or empty rail|tools tracks (right gutter)
  - Early change-form 2-col that strands tools (right void)
  - Decide card hard-capped narrow gutters
  - Double mx-4 inset on already-padded admin banners

Wired into: scripts/audit_admin_os_cross_wave.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V15 = ROOT / "static/css/rmc-admin-approval-surface-v15.css"
CONTRACT = ROOT / "static/css/rmc-admin-django-canvas-contract.css"
BASE_SITE = ROOT / "templates/admin/base_site.html"
INDEX_OP = ROOT / "templates/admin/index_superadmin.html"
INDEX_T = ROOT / "templates/admin/index_tenant.html"
SITECONFIG_APP = ROOT / "templates/admin/siteconfig/app_index.html"
CHANGE_FORM = ROOT / "templates/admin/change_form.html"
CHANGE_LIST = ROOT / "templates/admin/change_list.html"
APP_INDEX = ROOT / "templates/admin/app_index.html"
DECIDE = ROOT / "templates/admin/delete_confirmation.html"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def main() -> int:
    errors: list[str] = []
    v15 = _read(V15)
    contract = _read(CONTRACT)
    base_site = _read(BASE_SITE)
    index_op = _read(INDEX_OP)
    index_t = _read(INDEX_T)
    siteconfig = _read(SITECONFIG_APP)
    change_form = _read(CHANGE_FORM)
    change_list = _read(CHANGE_LIST)
    app_index = _read(APP_INDEX)
    decide = _read(DECIDE)

    compact_v15 = re.sub(r"\s+", "", v15)
    compact_base = re.sub(r"\s+", "", base_site)

    # --- Discover uses approved desktop tracks and <=1024 one-column collapse. ---
    if '[data-rmc-admin-index-canvas="operator"][data-rmc-admin-discover="1"]' not in v15:
        errors.append("v15 CSS missing Discover operator dual-attr seal")
    if '[data-rmc-admin-index-canvas="tenant"][data-rmc-admin-discover="1"]' not in v15:
        errors.append("v15 CSS missing Discover tenant dual-attr seal")
    if '[data-rmc-admin-index-canvas="operator"][data-rmc-admin-discover="1"]' not in base_site:
        errors.append("critical inline CSS missing Discover dual-attr seal (operator)")
    if '[data-rmc-admin-index-canvas="tenant"][data-rmc-admin-discover="1"]' not in base_site:
        errors.append("critical inline CSS missing Discover dual-attr seal (tenant)")
    operator_grid = "grid-template-columns:minmax(0,1fr)minmax(9.2rem,17%)2.35rem!important"
    tenant_grid = "grid-template-columns:minmax(0,1fr)minmax(9.5rem,18%)2.35rem!important"
    if operator_grid not in compact_v15 or operator_grid not in compact_base:
        errors.append("operator Discover grid must match approved minmax(0,1fr) minmax(9.2rem,17%) 2.35rem")
    if tenant_grid not in compact_v15 or tenant_grid not in compact_base:
        errors.append("tenant Discover grid must match approved minmax(0,1fr) minmax(9.5rem,18%) 2.35rem")
    if "@media(max-width:1024px)" not in compact_v15:
        errors.append("v15 CSS missing <=1024 single-column responsive gate")

    # --- Ban phantom tools track (≤1180 used to reserve 3rem while tools were display:none) ---
    if re.search(
        r"grid-template-columns:\s*minmax\(\s*0\s*,\s*1fr\s*\)\s+3rem",
        contract,
    ) or re.search(
        r"grid-template-columns:\s*minmax\(\s*0\s*,\s*1fr\s*\)\s+3rem",
        v15,
    ):
        errors.append(
            "ban grid-template-columns: minmax(0,1fr) 3rem — phantom tools gutter "
            "(tools are hidden at ≤1180; use 1fr only)"
        )

    # --- Early change-form must not be 2-col sidecar-only (strands tools) ---
    # Look for the early "Change forms:" block pattern with sidecar without tools track.
    early = contract[: contract.find("2026-07-17 intelligent-index")] if "2026-07-17 intelligent-index" in contract else contract[:2500]
    if re.search(
        r"change-form\s+\.rmc-admin-workspace[^{]*\{[^}]*"
        r"grid-template-columns:\s*minmax\(0,\s*1fr\)\s+var\(--rmc-django-sidecar\)",
        early,
        re.S,
    ):
        errors.append(
            "canvas-contract early change-form still uses 2-col sidecar "
            "(strands tools → right void); must be approval 3-col"
        )
    if "minmax(9.2rem, 17%) 2.35rem" not in early and "minmax(9.2rem,17%) 2.35rem" not in early.replace(" ", ""):
        # Soft: early block should declare 3-col
        if "Change forms:" in early and "2.35rem" not in early:
            errors.append("canvas-contract early change-form block missing tools track 2.35rem")

    # --- Decide: no narrow 40rem card gutters ---
    if "min(100%, 40rem)" in v15 or "min(100%,40rem)" in v15.replace(" ", ""):
        errors.append("Decide card must not hard-cap at 40rem (use full canvas width)")
    if "place-items: start center" in v15:
        errors.append("Decide canvas must not center a narrow card (place-items start stretch)")

    # --- Templates: Discover rail/tools tracks must be contentful. ---
    for label, src in (("operator index", index_op), ("tenant index", index_t)):
        if "admin_workspace_tools.html" not in src:
            errors.append(f"{label} missing approved page-aware tools strip")
        if "admin_index_context_rail.html" not in src:
            errors.append(f"{label} missing approved page-aware context rail")
        if 'data-rmc-admin-discover="1"' not in src:
            errors.append(f"{label} missing data-rmc-admin-discover=1")

    # --- Edit/Scan keep tools (contentful tracks, not empty) ---
    if "admin_workspace_tools.html" not in change_form:
        errors.append("change_form must mount tools (Edit 3-col contentful)")
    if "admin_workspace_tools.html" not in change_list:
        errors.append("change_list must mount tools (Scan 3-col contentful)")
    if "rmc-admin-dossier-canvas" not in app_index:
        errors.append("app_index must use rmc-admin-dossier-canvas")
    if ".rmc-admin-dossier-canvas" not in contract and "rmc-admin-dossier-canvas" not in contract:
        errors.append("canvas-contract must style .rmc-admin-dossier-canvas (app-index)")

    # --- Double inset banners ---
    if re.search(r'class="[^"]*\bmx-4\b[^"]*"', index_op) and "rmc-admin-discover-canvas" in index_op:
        # Allow mx-4 only if not on primary discover chrome; flag banner/canvas
        if "mx-4 mt-3" in index_op or 'discover-canvas mx-4' in index_op or "mx-4\" data-rmc-admin-index-canvas" in index_op:
            errors.append("operator index still uses mx-4 on discover chrome (double inset)")
    if "mx-4" in siteconfig and "Prefer the control plane" in siteconfig:
        errors.append("siteconfig/app_index banner must not use mx-4 (page body already padded)")

    # --- Decide template present ---
    if 'data-rmc-admin-archetype="decide"' not in decide:
        errors.append("delete_confirmation must be Decide archetype")

    if errors:
        print("ADMIN_OS_EMPTY_SPACE_FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("ADMIN_OS_EMPTY_SPACE_PASS")
    print("  discover=approved-3-col-responsive edit/scan=3-col-contentful decide=full-bleed dossier=aligned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
