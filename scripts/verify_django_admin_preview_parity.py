#!/usr/bin/env python3
"""Gate live Django admin CSS/templates against approved design-preview HTML.

Approval sources of truth (do not invent ratios):
  var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html
  var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html

PASS when live shell carries the same workspace grid + table.fill contract.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OPERATOR_PREVIEW = (
    ROOT
    / "var/design-previews/django-admin-page-aware-full-fill-approval-2026-07-19.html"
)
TENANT_PREVIEW = (
    ROOT / "var/design-previews/tenant-admin-config-engine-approval-2026-07-19.html"
)
CANVAS_CSS = ROOT / "static/css/rmc-admin-django-canvas-contract.css"
BASE_SITE = ROOT / "templates/admin/base_site.html"
SUBMIT_LINE = ROOT / "templates/admin/submit_line.html"
INDEX_TENANT = ROOT / "templates/admin/index_tenant.html"
CHANGE_FORM = ROOT / "templates/admin/change_form.html"
CHANGE_LIST = ROOT / "templates/admin/change_list.html"

SEAL = "2026-07-20-preview-parity-sot"
CACHE_BUST = "20260720-admin-preview-parity-v7"

_WS_GRID_RE = re.compile(
    r"\.ws\s*\{[^}]*grid-template-columns\s*:\s*([^;}]+)",
    re.I | re.S,
)
_NORMALIZE = re.compile(r"\s+")


def _norm(s: str) -> str:
    return _NORMALIZE.sub("", s.strip().lower())


def _extract_ws_grid(preview: Path) -> str:
    text = preview.read_text(encoding="utf-8")
    m = _WS_GRID_RE.search(text)
    if not m:
        raise SystemExit(f"PREVIEW_PARITY_FAIL: no .ws grid-template-columns in {preview}")
    return _norm(m.group(1))


def main() -> int:
    errors: list[str] = []

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

    # Expected from approval HTML (normalized)
    if op_grid != _norm("minmax(0,1fr) minmax(9.2rem,17%) 2.35rem"):
        errors.append(f"operator preview .ws grid drifted: {op_grid}")
    if ten_grid != _norm("minmax(0,1fr) minmax(9.5rem,18%) 2.35rem"):
        errors.append(f"tenant preview .ws grid drifted: {ten_grid}")

    css = CANVAS_CSS.read_text(encoding="utf-8") if CANVAS_CSS.is_file() else ""
    base = BASE_SITE.read_text(encoding="utf-8") if BASE_SITE.is_file() else ""
    submit = SUBMIT_LINE.read_text(encoding="utf-8") if SUBMIT_LINE.is_file() else ""
    index_t = INDEX_TENANT.read_text(encoding="utf-8") if INDEX_TENANT.is_file() else ""
    change_form = CHANGE_FORM.read_text(encoding="utf-8") if CHANGE_FORM.is_file() else ""
    change_list = CHANGE_LIST.read_text(encoding="utf-8") if CHANGE_LIST.is_file() else ""

    if SEAL not in css:
        errors.append(f"canvas CSS missing terminal seal {SEAL}")

    # Live must contain the approval grid formulas (whitespace-insensitive).
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

    # Terminal seal must prefer table-layout:fixed (preview table.fill).
    seal_idx = css.find(SEAL)
    if seal_idx >= 0:
        seal_tail = css[seal_idx:]
        if "table-layout: fixed" not in seal_tail and "table-layout:fixed" not in seal_tail:
            errors.append(f"{SEAL} must set table-layout: fixed (preview table.fill)")
        # Ban regressing to the pre-approval wide rail inside the seal block.
        if re.search(
            r"minmax\(\s*15rem\s*,\s*min\(\s*22vw",
            seal_tail,
        ):
            errors.append(f"{SEAL} must not reintroduce minmax(15rem, min(22vw…)) wide rail")

    if f"?v={CACHE_BUST}" not in base:
        errors.append(f"base_site must cache-bust canvas CSS with ?v={CACHE_BUST}")
    if 'data-rmc-admin-preview-parity="2026-07-20"' not in base:
        errors.append("base_site must emit inline #rmc-admin-preview-parity-critical")
    if "minmax(9.2rem, 17%)" not in base and "minmax(9.2rem,17%)" not in base:
        errors.append("inline preview-parity critical CSS must include operator 9.2rem/17% grid")

    if "rmc-django-save-compact" not in submit:
        errors.append("submit_line.html must implement compact Save (preview save-compact)")
    if "School configuration engine" not in index_t:
        errors.append("index_tenant.html must label School configuration engine (tenant approval)")
    if 'data-rmc-django-workspace="change-form"' not in change_form:
        errors.append("change_form.html missing data-rmc-django-workspace=change-form")
    if 'data-rmc-django-workspace="change-list"' not in change_list:
        errors.append("change_list.html missing data-rmc-django-workspace=change-list")
    if "admin_workspace_tools.html" not in change_form or "admin_workspace_tools.html" not in change_list:
        errors.append("change_form/change_list must include workspace tools (preview col-3)")

    if 'data-rmc-admin-approval-build="2026-07-20-v7"' not in (
        ROOT / "templates/admin/base.html"
    ).read_text(encoding="utf-8"):
        errors.append("admin/base.html must emit data-rmc-admin-approval-build=2026-07-20-v7")
    if "Staff accounts" not in index_t:
        errors.append("index_tenant.html must show Staff accounts KPI (approval Surface 1)")
    if "v7 · approval canvas" not in index_t and "approval canvas" not in index_t:
        errors.append("index_tenant.html must show visible approval build chip")
    if "Search school settings, people, academics" not in (
        ROOT / "templates/components/admin_nav_bridge.html"
    ).read_text(encoding="utf-8"):
        errors.append("admin_nav_bridge must use approval search placeholder")

    # Ban regressing wide/2-col workbench rails anywhere in live canvas CSS.
    # These are the exact formulas that left empty right gutters + stranded TOOLS.
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

    workspace_10x = (ROOT / "static/css/rmc-admin-workspace-10x.css").read_text(
        encoding="utf-8"
    )
    if "clamp(260px, 20vw, 330px)" in workspace_10x:
        errors.append("workspace-10x still forces 2-col clamp(260px…) — approval is 3-col")
    if "minmax(9.2rem, 17%)" not in workspace_10x and "minmax(9.2rem,17%)" not in workspace_10x:
        errors.append("workspace-10x must use operator approval grid minmax(9.2rem, 17%)")

    if "2026-07-20-preview-parity-specificity" not in css:
        errors.append(
            "canvas CSS missing 2026-07-20-preview-parity-specificity (#cp-main-content beat)"
        )
    if "#cp-main-content" not in base:
        errors.append("inline preview-parity critical CSS must include #cp-main-content beat")
    seal_and_after = css[css.find(SEAL) :] if SEAL in css else ""
    if "#cp-main-content" not in seal_and_after:
        errors.append(
            f"{SEAL} (or later) must include #cp-main-content specificity override"
        )

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print("PREVIEW_PARITY_FAIL")
        return 1

    print("PREVIEW_PARITY_PASS")
    print(f"  operator .ws = {op_grid}")
    print(f"  tenant   .ws = {ten_grid}")
    print(f"  seal     = {SEAL}")
    print(f"  cache    = {CACHE_BUST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
