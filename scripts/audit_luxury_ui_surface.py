#!/usr/bin/env python3
"""
Luxury UI integration audit (high-impact + governed surfaces).

Scores 15 points across seven dimensions: layout consistency, component consistency,
overflow safety, click depth, mobile UX, action clarity, state handling.

Exit codes: 0 = success (severe integration checks pass and score >= 13 unless overridden).
1 = severe violations (shell / inline / unwrapped tables / missing table-family on violated majors).
2 = luxury score gate failed (use --allow-below-luxury-gate to override).

Writes docs/generated/luxury_ui_audit.json and luxury_ui_audit.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "docs" / "generated" / "luxury_ui_audit.json"
OUT_MD = ROOT / "docs" / "generated" / "luxury_ui_audit.md"

TEMPLATE_ROOT = ROOT / "templates"
CSS_ROOT = ROOT / "static" / "css"

SHELL_TEMPLATES = [
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_base.html",
    "templates/control_plane_skeleton.html",
]

MAJOR_SCREENS = [
    "templates/accounts/backend_dashboard.html",
    "templates/schools/super_dashboard.html",
    "templates/schools/billing_dashboard.html",
    "templates/super/founder_dashboard.html",
    "templates/marketplace/tenant_app_catalog.html",
    "templates/marketplace/tenant_installed_apps.html",
    "templates/teacher/dashboard.html",
    "templates/teacher/marks_list.html",
    "templates/teacher/attendance.html",
    "templates/parent/dashboard.html",
    "templates/parent/attendance_discipline.html",
    "templates/student360/student_360_page.html",
    "templates/siteconfig/tenant_runtime_configuration_hub.html",
    "templates/siteconfig/billing_plan_readonly.html",
    "templates/siteconfig/console_domains_hub.html",
    "templates/studio_os/shell.html",
    "templates/reports/annual_report.html",
    "templates/reports/term_report.html",
    "templates/sales/pipeline_board.html",
]

GOVERNED_CSS = [
    "static/css/design-tokens-luxury.css",
    "static/css/design-system-unified.css",
    "static/css/platform-high-end.css",
    "static/css/design-system-phase2-enforcement.css",
]

THEME_CSS = [
    "static/css/control-plane-ultra.css",
    "static/css/portal-premium-shell.css",
    "static/css/table-system.css",
    "static/css/form-system.css",
    "static/css/card-grammar.css",
]

ALL_AUDITED_CSS = GOVERNED_CSS + THEME_CSS

INLINE_STYLE_ATTR = re.compile(r"\sstyle\s*=", re.IGNORECASE)
INLINE_STYLE_CAPTURE = re.compile(
    r"(?<![\w-])style\s*=\s*\"([^\"]*)\"|(?<![\w-])style\s*=\s*'([^']*)'",
    re.IGNORECASE,
)
INLINE_STYLE_TAG = re.compile(r"<style\b", re.IGNORECASE)
SCRIPT_BLOCK = re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL)
ALLOWED_STYLE_TAG_MARKERS = (
    "id=\"root-base-theme-vars\"",
    "data-site-custom-css",
    "block theme_root_variables",
)
TABLE_TAG = re.compile(r"<table\b", re.IGNORECASE)
TABLE_OPEN_TAG = re.compile(r"<table\b[^>]*>", re.IGNORECASE)
OVERFLOW_RISK = re.compile(
    r"(?:width\s*:\s*100vw|min-width\s*:\s*(?:1[0-9]{2,}|[2-9][0-9]{2,})px|overflow-x\s*:\s*visible)",
    re.IGNORECASE,
)
RAW_SPACING_PROP = re.compile(
    r"^\s*(?:margin|padding|gap|row-gap|column-gap|"
    r"padding-(?:top|right|bottom|left|block|inline)|"
    r"margin-(?:top|right|bottom|left|block|inline))\s*:\s*"
    r"(?!var\()(-?\d*\.?\d+(?:px|rem|em|vh|vw|%)\b)",
    re.IGNORECASE,
)
RAW_RADIUS_PROP = re.compile(
    r"^\s*border-radius(?:-[a-z-]+)?\s*:\s*(?!var\()"
    r"(-?\d*\.?\d+(?:px|rem|em|%)\b)",
    re.IGNORECASE,
)
RAW_SHADOW_PROP = re.compile(r"^\s*box-shadow\s*:\s*(?!var\()(.+);", re.IGNORECASE)
VAR_DEF = re.compile(r"^\s*--[a-zA-Z0-9-_]+\s*:")
GLOBAL_COMPONENT_SELECTOR = re.compile(r"^\s*(\.card|\.btn-primary|\.form-control|\.table)(?=[\s,{])", re.IGNORECASE)
TOKENS_IN_LINKED_PARENT = ("control_plane_skeleton.html", "portal_base.html", "base.html")
HIGH_IMPACT_PATTERNS = (
    "templates/studio_os/**/*.html",
    "templates/siteconfig/**/*.html",
    "templates/reports/**/*.html",
)

EXTENDS_RE = re.compile(r"\{%\s*extends\s+[\"']([^\"']+)[\"']\s*%\}")

DIMENSION_MAX = {
    "layout_consistency": 2,
    "component_consistency": 2,
    "overflow_safety": 2,
    "click_depth": 2,
    "mobile_ux": 2,
    "action_clarity": 3,
    "state_handling": 2,
}

STATE_HINT_PATTERN = re.compile(
    r"(loading_empty_states\.html|studio-os-loading|studio-os-empty|role=\"alert\"|"
    r"aria-busy|empty-state|permission\s+denied|offline|data-offline|retry|403\s|forbidden|"
    r"try again|access denied|connection)",
    re.IGNORECASE,
)

# Phase 5 state matrix (informational; not part of numeric score)
_STATE_MATRIX_PATTERNS: dict[str, re.Pattern[str]] = {
    "loading": re.compile(
        r"(loading_empty_states|aria-busy|skeleton|spinner|studio-os-loading|data-loading)",
        re.IGNORECASE,
    ),
    "empty": re.compile(
        r"(empty-state|studio-os-empty|no data yet|no items|list is empty)",
        re.IGNORECASE,
    ),
    "error": re.compile(
        r'(role="alert"|alert-danger|class="alert alert-danger"|error-state|has-error)',
        re.IGNORECASE,
    ),
    "permission_denied": re.compile(
        r"(permission denied|access denied|403|forbidden|not allowed to)",
        re.IGNORECASE,
    ),
    "offline": re.compile(r"(data-offline|offline|connection lost|navigator\.onLine)", re.IGNORECASE),
    "retry": re.compile(r"(retry|try again|reload this page|tap to retry)", re.IGNORECASE),
}


def _read(rel: str) -> str:
    p = ROOT / rel
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def _path_exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _high_impact_templates() -> list[str]:
    files = set(MAJOR_SCREENS + SHELL_TEMPLATES)
    for pat in HIGH_IMPACT_PATTERNS:
        for p in ROOT.glob(pat):
            if p.is_file():
                files.add(str(p.relative_to(ROOT)).replace("\\", "/"))
    return sorted(files)


def _classify_rows(paths: list[str], severe_paths: set[str]) -> dict[str, object]:
    violation = sorted([p for p in paths if p in severe_paths])
    needs_review = sorted([p for p in paths if p not in severe_paths])
    return {
        "count": len(paths),
        "violation_count": len(violation),
        "needs_review_count": len(needs_review),
        "violation_paths": violation,
        "needs_review_paths": needs_review,
    }


def _scan_inline_styles(paths: list[str]) -> dict[str, object]:
    hits: list[str] = []
    for rel in paths:
        text = _read(rel)
        if not text:
            continue
        scrubbed = SCRIPT_BLOCK.sub("", text)
        style_attr_hit = False
        for m in INLINE_STYLE_CAPTURE.finditer(scrubbed):
            value = (m.group(1) or m.group(2) or "").strip()
            if "{{" in value or "{%" in value:
                continue
            style_attr_hit = True
            break
        style_tag_hit = INLINE_STYLE_TAG.search(scrubbed) is not None
        style_tag_allowed = any(m in scrubbed for m in ALLOWED_STYLE_TAG_MARKERS) if style_tag_hit else True
        if style_attr_hit or (style_tag_hit and not style_tag_allowed):
            hits.append(rel)
    severe = set(SHELL_TEMPLATES)
    return _classify_rows(sorted(hits), severe)


def _scan_unwrapped_tables(paths: list[str]) -> dict[str, object]:
    hits: list[str] = []
    for rel in paths:
        text = _read(rel)
        if not TABLE_TAG.search(text):
            continue
        table_tags = TABLE_OPEN_TAG.findall(text)
        requires_wrap = any("class=" in t and "table" in t for t in table_tags)
        if not requires_wrap:
            continue
        wrapped = any(
            marker in text
            for marker in ("table-responsive", "ds-table-wrap", "table-wrap", "overflow-auto")
        )
        if not wrapped:
            hits.append(rel)
    severe = {p for p in MAJOR_SCREENS if "/reports/" not in p}
    return _classify_rows(sorted(hits), severe)


def _scan_missing_table_family(paths: list[str]) -> dict[str, object]:
    hits: list[str] = []
    for rel in paths:
        text = _read(rel)
        if "<table" not in text:
            continue
        table_tags = TABLE_OPEN_TAG.findall(text)
        requires_family = any("class=" in t and "table" in t for t in table_tags)
        if not requires_family:
            continue
        has_family = any("table-family" in t for t in table_tags)
        if not has_family:
            hits.append(rel)
    severe = set(MAJOR_SCREENS)
    return _classify_rows(sorted(hits), severe)


def _scan_missing_ds_btn(paths: list[str]) -> dict[str, object]:
    hits: list[str] = []
    for rel in paths:
        text = _read(rel)
        if "btn" in text and "ds-btn" not in text:
            hits.append(rel)
    severe = set()  # advisory only for now
    return _classify_rows(sorted(hits), severe)


def _screen_header_action_bar_status() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    missing_header = 0
    missing_action_bar = 0
    for rel in MAJOR_SCREENS:
        text = _read(rel)
        if not text:
            rows.append({"path": rel, "exists": False, "header": False, "action_bar": False})
            missing_header += 1
            missing_action_bar += 1
            continue
        has_header = any(
            marker in text
            for marker in (
                "components/page_header.html",
                "data-page-header",
                "class=\"page-header",
                "<h1",
            )
        )
        has_action = any(
            marker in text
            for marker in (
                "ds-action-bar",
                "action-bar",
                "page_families/action_bar.html",
                "components/pagination.html",
            )
        )
        if not has_header:
            missing_header += 1
        if not has_action:
            missing_action_bar += 1
        rows.append({"path": rel, "exists": True, "header": has_header, "action_bar": has_action})
    severe_missing_header = [
        r["path"] for r in rows if r["exists"] and not r["header"] and r["path"] in MAJOR_SCREENS
    ]
    severe_missing_action = [
        r["path"] for r in rows if r["exists"] and not r["action_bar"] and r["path"] in MAJOR_SCREENS
    ]
    return {
        "rows": rows,
        "missing_headers": missing_header,
        "missing_action_bars": missing_action_bar,
        "header_violations": severe_missing_header,
        "action_bar_violations": severe_missing_action,
    }


def _shell_consistency() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    fail = 0
    for rel in SHELL_TEMPLATES:
        text = _read(rel)
        extends_parent = (
            "extends \"control_plane_skeleton.html\"" in text
            or "extends 'control_plane_skeleton.html'" in text
            or "extends \"portal_base.html\"" in text
            or "extends 'portal_base.html'" in text
            or "extends \"base.html\"" in text
            or "extends 'base.html'" in text
        )
        has_tokens = ("design-tokens.css" in text) or extends_parent
        has_enforcement = ("design-system-phase2-enforcement.css" in text) or extends_parent
        has_main = any(
            x in text
            for x in (
                "id=\"main-content\"",
                "id=\"cp-main-content\"",
                "role=\"main\"",
                "<main",
                "data-rmc-shell-main",
            )
        )
        ok = bool(text) and has_tokens and has_enforcement and has_main
        if not ok:
            fail += 1
        rows.append(
            {
                "path": rel,
                "ok": ok,
                "has_tokens": has_tokens,
                "has_enforcement": has_enforcement,
                "has_main_region": has_main,
            }
        )
    return {"rows": rows, "failures": fail}


def _scan_css_non_token_literals() -> dict[str, object]:
    per_file: dict[str, dict[str, int]] = {}
    totals = {"spacing": 0, "radius": 0, "shadow": 0}
    for rel in ALL_AUDITED_CSS:
        p = ROOT / rel
        text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        spacing = radius = shadow = 0
        for line in text.splitlines():
            s = line.strip()
            if not s or VAR_DEF.match(s):
                continue
            if RAW_SPACING_PROP.search(s):
                spacing += 1
            if RAW_RADIUS_PROP.search(s):
                radius += 1
            if RAW_SHADOW_PROP.search(s):
                shadow += 1
        totals["spacing"] += spacing
        totals["radius"] += radius
        totals["shadow"] += shadow
        per_file[rel] = {"spacing": spacing, "radius": radius, "shadow": shadow}
    return {"totals": totals, "per_file": per_file}


def _scan_overflow_risks() -> dict[str, object]:
    css_hits: list[str] = []
    for rel in ALL_AUDITED_CSS:
        text = _read(rel)
        if OVERFLOW_RISK.search(text):
            css_hits.append(rel)
    tpl_hits: list[str] = []
    for rel in _high_impact_templates():
        text = _read(rel)
        if "overflow-x-visible" in text or "style=\"width:100vw" in text:
            tpl_hits.append(rel)
    return {
        "css_count": len(css_hits),
        "css_paths": sorted(css_hits),
        "template_count": len(tpl_hits),
        "template_paths": sorted(tpl_hits),
    }


def _duplicate_component_systems() -> dict[str, object]:
    selectors = [".card", ".btn-primary", ".form-control", ".table"]
    index: dict[str, list[str]] = {s: [] for s in selectors}
    for rel in ALL_AUDITED_CSS:
        text = _read(rel)
        lines = text.splitlines()
        globals_for_file = set()
        for ln in lines:
            m = GLOBAL_COMPONENT_SELECTOR.search(ln)
            if not m:
                continue
            sel = m.group(1)
            globals_for_file.add(sel)
        for sel in selectors:
            if sel in globals_for_file:
                index[sel].append(rel)
    conflict_count = 0
    for sel, files in index.items():
        if len(files) >= 3:
            conflict_count += 1
    return {"selector_index": index, "conflict_count": conflict_count}


def _tenant_branding_safety() -> dict[str, object]:
    hits: list[str] = []
    direct_text_color = re.compile(r"^\s*color\s*:\s*var\(--school-primary", re.IGNORECASE)
    for rel in ALL_AUDITED_CSS:
        text = _read(rel)
        if any(direct_text_color.search(line.strip()) for line in text.splitlines()):
            hits.append(rel)
    unified = _read("static/css/design-system-unified.css")
    has_dark_contrast = all(
        x in unified
        for x in (
            "--color-text-primary",
            "--color-text-muted",
            "data-theme=\"dark\"",
            "color-mix(",
        )
    )
    return {
        "unsafe_direct_brand_text_count": len(hits),
        "unsafe_direct_brand_text_paths": sorted(hits),
        "has_dark_contrast_contract": has_dark_contrast,
    }


def _regional_rtl_status() -> dict[str, object]:
    p = ROOT / "docs" / "generated" / "regional_ui_surface_audit.json"
    if not p.is_file():
        return {"available": False, "violation": None, "needs_review": None}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"available": False, "violation": None, "needs_review": None}
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    return {
        "available": True,
        "violation": int(summary.get("violation", 0)),
        "needs_review": int(summary.get("needs_review", 0)),
    }


def _debug_surface_hits() -> dict[str, object]:
    hits: list[str] = []
    pattern = re.compile(r"\bDEBUG\b|raw debug|todo: debug|\{\{\s*debug", re.IGNORECASE)
    for p in TEMPLATE_ROOT.rglob("*.html"):
        text = p.read_text(encoding="utf-8", errors="replace")
        if pattern.search(text):
            hits.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return {"count": len(hits), "paths": sorted(hits)}


def _zero_click_resolved(rel: str, depth: int = 0, seen: set[str] | None = None) -> bool:
    """True if template inherits the shared strip, embeds it, or is explicitly exempt (e.g. print)."""
    if depth > 14:
        return False
    if seen is None:
        seen = set()
    if rel in seen:
        return False
    seen.add(rel)
    text = _read(rel)
    if not text:
        return False
    if "data-rmc-zero-click-exempt" in text or "rmc-zero-click-exempt" in text:
        return True
    if "rmc_zero_click_command_strip" in text or "data-rmc-zero-click" in text:
        return True
    m = EXTENDS_RE.search(text)
    if not m:
        return False
    parent = f"templates/{m.group(1)}"
    return _zero_click_resolved(parent, depth + 1, seen)


def _zero_click_major_surfaces() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    failures = 0
    for rel in MAJOR_SCREENS:
        ok = _zero_click_resolved(rel)
        if not ok:
            failures += 1
        rows.append({"path": rel, "zero_click_resolved": ok})
    return {"failure_count": failures, "rows": rows}


def _viewport_in_template_chain(rel: str, depth: int = 0, seen: set[str] | None = None) -> bool:
    """Shell children (e.g. control_plane_base) may inherit viewport from skeleton head."""
    if depth > 14:
        return False
    if seen is None:
        seen = set()
    if rel in seen:
        return False
    seen.add(rel)
    text = _read(rel)
    if not text:
        return False
    if 'name="viewport"' in text or "name='viewport'" in text:
        return True
    m = EXTENDS_RE.search(text)
    if not m:
        return False
    parent = f"templates/{m.group(1)}"
    return _viewport_in_template_chain(parent, depth + 1, seen)


def _shell_viewport_scan() -> dict[str, object]:
    missing: list[str] = []
    for rel in SHELL_TEMPLATES:
        if not _viewport_in_template_chain(rel):
            missing.append(rel)
    return {"missing_viewport_paths": sorted(missing), "ok": len(missing) == 0}


def _state_handling_major_screens() -> dict[str, object]:
    """Surface-level hints for loading / empty / error / retry — informational."""
    rows: list[dict[str, object]] = []
    weak = 0
    for rel in MAJOR_SCREENS:
        text = _read(rel)
        hit = bool(text and STATE_HINT_PATTERN.search(text))
        if not hit and text and ("data-rmc-zero-click-exempt" in text or "print-document" in text):
            hit = True
        if not hit:
            weak += 1
        rows.append({"path": rel, "state_hints_detected": hit})
    return {"rows": rows, "major_without_state_hints": weak}


def _state_completeness_matrix() -> dict[str, object]:
    """Per-major hints for loading / empty / error / permission / offline / retry (Phase 5 ledger)."""
    keys = tuple(_STATE_MATRIX_PATTERNS.keys())
    rows: list[dict[str, object]] = []
    for rel in MAJOR_SCREENS:
        text = _read(rel)
        hits = {k: bool(text and _STATE_MATRIX_PATTERNS[k].search(text)) for k in keys}
        resolved = _zero_click_resolved(rel)
        exempt_print = bool(text and ("data-rmc-zero-click-exempt" in text or "print-document" in text))
        rows.append(
            {
                "path": rel,
                "zero_click_shell_or_exempt": resolved or exempt_print,
                **hits,
            }
        )
    coverage = {k: sum(1 for r in rows if r.get(k)) for k in keys}
    return {"keys": list(keys), "rows": rows, "major_screen_count": len(MAJOR_SCREENS), "coverage_counts": coverage}


def _penalty_dimension_keys(payload: dict[str, object]) -> list[str]:
    """Mirrors `_compute_score` deductions as dimension labels (length equals 15 - score)."""
    out: list[str] = []
    inline_viol = int(payload["inline_styles"]["violation_count"])  # type: ignore[index]
    for _ in range(min(3, inline_viol)):
        out.append("component_consistency")
    unwrapped_viol = int(payload["unwrapped_tables"]["violation_count"])  # type: ignore[index]
    for _ in range(min(2, unwrapped_viol)):
        out.append("overflow_safety")
    shell_fail = int(payload["shell_consistency"]["failures"])  # type: ignore[index]
    for _ in range(min(2, shell_fail)):
        out.append("layout_consistency")
    missing_headers = int(payload["screen_headers_actions"]["missing_headers"])  # type: ignore[index]
    missing_actions = int(payload["screen_headers_actions"]["missing_action_bars"])  # type: ignore[index]
    if (missing_headers + missing_actions) > 4:
        out.append("action_clarity")
    if int(payload["overflow_risks"]["template_count"]) > 0:  # type: ignore[index]
        out.append("overflow_safety")
    t = payload["non_token_literals"]["totals"]  # type: ignore[index]
    raw_total = int(t["spacing"]) + int(t["radius"]) + int(t["shadow"])
    if raw_total > 35:
        out.append("layout_consistency")
    if int(payload["duplicate_component_systems"]["conflict_count"]) > 0:  # type: ignore[index]
        out.append("component_consistency")
    if int(payload["tenant_branding_safety"]["unsafe_direct_brand_text_count"]) > 0:  # type: ignore[index]
        out.append("mobile_ux")
    rtl_violation = int((payload["rtl_status"]["violation"] or 0))  # type: ignore[index]
    if rtl_violation > 0:
        out.append("mobile_ux")
    if int(payload["debug_surface_hits"]["count"]) > 0:  # type: ignore[index]
        out.append("state_handling")
    return out


def _apply_dimension_penalties(penalties: list[str]) -> dict[str, int]:
    dims = {k: DIMENSION_MAX[k] for k in DIMENSION_MAX}
    spill_order = [
        "action_clarity",
        "layout_consistency",
        "component_consistency",
        "overflow_safety",
        "click_depth",
        "mobile_ux",
        "state_handling",
    ]
    for p in penalties:
        key = p if p in dims else "layout_consistency"
        if dims[key] > 0:
            dims[key] -= 1
            continue
        for s in spill_order:
            if dims[s] > 0:
                dims[s] -= 1
                break
    return dims


def _dimension_breakdown(payload: dict[str, object], legacy_score: int) -> dict[str, object]:
    penalties = _penalty_dimension_keys(payload)
    dims = _apply_dimension_penalties(penalties)
    zc = payload.get("zero_click_contract") if isinstance(payload.get("zero_click_contract"), dict) else {}
    fail_count = int(zc.get("failure_count", 0))  # type: ignore[arg-type]
    if fail_count > 0:
        take = min(fail_count, dims["click_depth"])
        dims["click_depth"] -= take
        give_back = take
        for g in ("action_clarity", "mobile_ux", "state_handling", "layout_consistency"):
            if give_back <= 0:
                break
            room = DIMENSION_MAX[g] - dims[g]
            add = min(room, give_back)
            dims[g] += add
            give_back -= add

    total = sum(dims.values())
    if total != legacy_score:
        drift = legacy_score - total
        order = ["action_clarity", "click_depth", "layout_consistency", "state_handling"]
        i = 0
        while drift != 0 and i < 100:
            k = order[i % len(order)]
            if drift > 0 and dims[k] < DIMENSION_MAX[k]:
                dims[k] += 1
                drift -= 1
            elif drift < 0 and dims[k] > 0:
                dims[k] -= 1
                drift += 1
            i += 1

    return {
        k: {"score": dims[k], "max": DIMENSION_MAX[k]}
        for k in DIMENSION_MAX
    }


def _compute_score(payload: dict[str, object]) -> int:
    score = 15
    inline_viol = int(payload["inline_styles"]["violation_count"])  # type: ignore[index]
    unwrapped_viol = int(payload["unwrapped_tables"]["violation_count"])  # type: ignore[index]
    missing_headers = int(payload["screen_headers_actions"]["missing_headers"])  # type: ignore[index]
    missing_actions = int(payload["screen_headers_actions"]["missing_action_bars"])  # type: ignore[index]
    raw_spacing = int(payload["non_token_literals"]["totals"]["spacing"])  # type: ignore[index]
    raw_radius = int(payload["non_token_literals"]["totals"]["radius"])  # type: ignore[index]
    raw_shadow = int(payload["non_token_literals"]["totals"]["shadow"])  # type: ignore[index]
    duplicates = int(payload["duplicate_component_systems"]["conflict_count"])  # type: ignore[index]
    unsafe_brand = int(payload["tenant_branding_safety"]["unsafe_direct_brand_text_count"])  # type: ignore[index]
    debug_hits = int(payload["debug_surface_hits"]["count"])  # type: ignore[index]
    shell_fail = int(payload["shell_consistency"]["failures"])  # type: ignore[index]
    rtl_violation = int((payload["rtl_status"]["violation"] or 0))  # type: ignore[index]

    score -= min(3, inline_viol)
    score -= min(2, unwrapped_viol)
    score -= min(2, shell_fail)
    score -= 1 if (missing_headers + missing_actions) > 4 else 0
    score -= 1 if int(payload["overflow_risks"]["template_count"]) > 0 else 0  # type: ignore[index]
    score -= 1 if (raw_spacing + raw_radius + raw_shadow) > 35 else 0
    score -= 1 if duplicates > 0 else 0
    score -= 1 if unsafe_brand > 0 else 0
    score -= 1 if rtl_violation > 0 else 0
    score -= 1 if debug_hits > 0 else 0
    return max(0, score)


def _verdict(score: int) -> str:
    if score >= 13:
        return "ULTRA-LUXURY"
    if score >= 9:
        return "LUXURY-READY"
    return "FAILURE"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--allow-below-luxury-gate",
        action="store_true",
        help="Do not exit non-zero when score < 13 (default: enforce Phase 7 gate).",
    )
    ap.add_argument("--base", default=None, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    high_impact_templates = _high_impact_templates()
    payload: dict[str, object] = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "high_impact_templates_total": len(high_impact_templates),
        "inline_styles": _scan_inline_styles(high_impact_templates),
        "unwrapped_tables": _scan_unwrapped_tables(high_impact_templates),
        "missing_table_family": _scan_missing_table_family(high_impact_templates),
        "missing_ds_btn": _scan_missing_ds_btn(high_impact_templates),
        "screen_headers_actions": _screen_header_action_bar_status(),
        "shell_consistency": _shell_consistency(),
        "non_token_literals": _scan_css_non_token_literals(),
        "overflow_risks": _scan_overflow_risks(),
        "duplicate_component_systems": _duplicate_component_systems(),
        "tenant_branding_safety": _tenant_branding_safety(),
        "rtl_status": _regional_rtl_status(),
        "debug_surface_hits": _debug_surface_hits(),
        "zero_click_contract": _zero_click_major_surfaces(),
        "mobile_viewport_contract": _shell_viewport_scan(),
        "state_handling_major_screens": _state_handling_major_screens(),
        "state_completeness_matrix": _state_completeness_matrix(),
    }
    score = _compute_score(payload)
    verdict = _verdict(score)
    payload["score_out_of_15"] = score
    payload["verdict"] = verdict
    payload["luxury_gate_min_score"] = 13
    payload["luxury_gate_passed"] = score >= 13
    payload["dimension_scores"] = _dimension_breakdown(payload, score)
    pcount = len(_penalty_dimension_keys(payload))
    if pcount != 15 - score:
        payload["dimension_score_drift_note"] = f"penalty_count {pcount} != 15 - score {15 - score}"

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = [
        "# Luxury UI Surface Audit",
        "",
        f"**Generated:** {payload['generated_at']}",
        f"**Score:** {score}/15",
        f"**Verdict:** {verdict}",
        "",
        "## Summary",
        "",
        f"- High-impact templates scanned: {payload['high_impact_templates_total']}",
        f"- Inline style hits: {payload['inline_styles']['count']} (violations: {payload['inline_styles']['violation_count']})",
        f"- Unwrapped tables: {payload['unwrapped_tables']['count']} (violations: {payload['unwrapped_tables']['violation_count']})",
        f"- Missing table-family: {payload['missing_table_family']['count']} (violations: {payload['missing_table_family']['violation_count']})",
        f"- Missing ds-btn usage: {payload['missing_ds_btn']['count']} (violations: {payload['missing_ds_btn']['violation_count']})",
        f"- Shell consistency failures: {payload['shell_consistency']['failures']}",
        f"- Overflow-prone CSS files: {payload['overflow_risks']['css_count']}",
        f"- Non-token literals (spacing/radius/shadow): {payload['non_token_literals']['totals']}",
        f"- Duplicate component-system conflicts: {payload['duplicate_component_systems']['conflict_count']}",
        f"- Unsafe direct brand text color hits: {payload['tenant_branding_safety']['unsafe_direct_brand_text_count']}",
        f"- RTL violations: {payload['rtl_status']['violation']}",
        f"- Debug-surface hits: {payload['debug_surface_hits']['count']}",
        f"- Zero-click major surfaces failing inheritance/exempt: {payload['zero_click_contract']['failure_count']}",
        f"- Shell viewport OK: {payload['mobile_viewport_contract']['ok']}",
        f"- Luxury gate (min 13): {'PASS' if payload.get('luxury_gate_passed') else 'FAIL'}",
        f"- State completeness matrix: {payload['state_completeness_matrix']['major_screen_count']} major templates",
        "",
        "## Dimension scores (/15 total)",
        "",
    ]
    ds = payload.get("dimension_scores") if isinstance(payload.get("dimension_scores"), dict) else {}
    for dk in sorted(ds.keys()):
        row = ds[dk]
        if isinstance(row, dict):
            md.append(f"- **{dk}:** {row.get('score')}/{row.get('max')}")
    md.extend(
        [
            "",
            "## Notes",
            "",
            "- This is a static audit focused on integration risk signals.",
            "- It is intended to complement verifier/test gates, not replace runtime visual QA.",
            "",
        ]
    )
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    work_queues = {
        "shell_contract": payload["shell_consistency"]["rows"],
        "duplicate_component_systems": payload["duplicate_component_systems"]["selector_index"],
        "inline_style_cleanup": payload["inline_styles"],
        "unwrapped_tables": payload["unwrapped_tables"],
        "overflow_risk_css": payload["overflow_risks"],
        "non_token_literals": payload["non_token_literals"],
        "tenant_theme_safety": payload["tenant_branding_safety"],
        "page_header_action_bar_contract": payload["screen_headers_actions"],
    }
    payload["work_queues"] = work_queues
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    gate_ok = bool(payload.get("luxury_gate_passed"))
    severe = bool(
        int(payload["shell_consistency"]["failures"]) > 0
        or int(payload["inline_styles"]["violation_count"]) > 0
        or int(payload["unwrapped_tables"]["violation_count"]) > 0
        or int(payload["missing_table_family"]["violation_count"]) > 0
    )
    if severe:
        print("FAIL: severe integration violations detected.", file=sys.stderr)
        return 1
    if not gate_ok and not args.allow_below_luxury_gate:
        print(
            f"FAIL: luxury gate — score {score}/15 < {payload['luxury_gate_min_score']} (use --allow-below-luxury-gate to override).",
            file=sys.stderr,
        )
        return 2
    print(
        f"audit_luxury_ui_surface: OK -> {OUT_JSON} | score={score}/15 verdict={verdict} gate={'PASS' if gate_ok else 'FAIL'}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
