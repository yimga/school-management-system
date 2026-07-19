#!/usr/bin/env python3
"""
Core vs Context + exceptional info-tag platform contract.

Locks the approved 2026-07-19 HTML:
- no fake admin KPIs
- rich tip layer JS
- admin info-tag bootstrap
- page explain on all authenticated shells (incl. tenant v3 + Django admin)
- globe dock not sr-clipped; deck-v2 hides orphan C/D voids
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> int:
    print(f"CORE_CONTEXT_INFO_FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    metrics = (ROOT / "templates/admin/includes/admin_workspace_metrics_strip.html").read_text(
        encoding="utf-8"
    )
    for banned in ("Canvas", "Form cap", "100%"):
        if banned in metrics:
            return _fail(f"fake KPI fluff remains in admin metrics: {banned}")
    if "rmc_info_tag" not in metrics:
        return _fail("admin metrics missing rmc_info_tag education")

    option_a = (ROOT / "templates/components/tenant_option_a_strip.html").read_text(
        encoding="utf-8"
    )
    if "rmc-option-a__lede" in option_a and "rmc_info_tag" not in option_a:
        return _fail("Option A still uses lede walls without info tags")
    if "rmc_info_tag" not in option_a:
        return _fail("Option A strip must use rmc_info_tag")

    tip_js = (ROOT / "static/js/rmc-info-tag.js").read_text(encoding="utf-8")
    for token in ("rmc-info-tip-layer", "data-rmc-info-what", "Watch outs"):
        if token not in tip_js:
            return _fail(f"rmc-info-tag.js missing exceptional tip token: {token}")

    tip_css = (ROOT / "static/css/rmc-class-grammar.css").read_text(encoding="utf-8")
    if ".rmc-info-tip-layer" not in tip_css:
        return _fail("rmc-class-grammar.css missing .rmc-info-tip-layer")

    base_site = (ROOT / "templates/admin/base_site.html").read_text(encoding="utf-8")
    if "rmc_tour_bootstrap.html" not in base_site:
        return _fail("admin/base_site.html must include rmc_tour_bootstrap for info tags")
    if "rmc_page_explain_strip.html" not in base_site:
        return _fail("admin/base_site.html missing page explain strip")

    for shell in (
        ROOT / "templates/base.html",
        ROOT / "templates/portal_base.html",
        ROOT / "templates/control_plane_base.html",
        ROOT / "templates/admin/base_site.html",
    ):
        text = shell.read_text(encoding="utf-8")
        if "rmc_page_explain_strip.html" not in text:
            return _fail(f"{shell.name} missing page explain strip")

    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    idx = portal.find("rmc_page_explain_strip.html")
    window = portal[max(0, idx - 180) : idx]
    if "not tp_v3_tenant_shell" in window:
        return _fail("tenant v3 still suppresses page explain strip")

    globe_css = (ROOT / "static/css/rmc-cp-200x.css").read_text(encoding="utf-8")
    if "clip: rect(0, 0, 0, 0)" in globe_css and "glass-dock--stacked" in globe_css:
        # Allow only if not applied to stacked dock as sr-only hide
        if (
            ".lx-world__glass-dock--stacked.lx-world__glass-dock--chrome-rail" in globe_css
            and "clip: rect(0, 0, 0, 0)" in globe_css[
                globe_css.find(".lx-world__glass-dock--stacked.lx-world__glass-dock--chrome-rail") :
                globe_css.find(".lx-world__glass-dock--stacked.lx-world__glass-dock--chrome-rail") + 280
            ]
        ):
            return _fail("globe glass dock still sr-clipped via clip:rect")

    live_map = (ROOT / "templates/partials/cockpit/_live_world_map.html").read_text(
        encoding="utf-8"
    )
    if "rmc-world-globe-chrome-dock-host-stacked" not in live_map:
        return _fail("globe chrome dock host missing")
    if "glass-dock--in-chrome" not in live_map:
        return _fail("globe dock must nest inside chrome rail host")

    if 'data-rmc-cp-globe-deck-v2="1"] .lx-world__map .lx-world__void-zone--chrome-rail-hide' not in globe_css:
        return _fail("deck-v2 landing must hide orphan C/D caption voids")

    rail_right = (ROOT / "templates/partials/cockpit/_globe_deck_rail_right.html").read_text(
        encoding="utf-8"
    )
    if "<button type=\"button\" class=\"rmc-globe-deck-v2__status-chip" not in rail_right:
        return _fail("globe right-rail status filters must be visible buttons")

    # Platform-wide Core vs Context (not Django-only)
    help_panel = (ROOT / "templates/components/workflow_help_panel.html").read_text(
        encoding="utf-8"
    )
    if "<details" not in help_panel or "rmc-workflow-help--compact" not in help_panel:
        return _fail("workflow_help_panel must collapse How-it-works by default")
    if "rmc_info_tag" not in help_panel:
        return _fail("workflow_help_panel must educate via rmc_info_tag")

    wc = (ROOT / "templates/accounts/workflow_center.html").read_text(encoding="utf-8")
    if "workflow_help_panel.html" in wc and "workflow_center_main.html" in wc:
        # Full-width include before main is banned; help must live in side rail of main
        if 'include "components/workflow_help_panel.html"' in wc:
            return _fail("workflow_center must not mount full-width How-it-works above canvas")

    hero = (ROOT / "templates/components/world_class_page_hero.html").read_text(
        encoding="utf-8"
    )
    if "rmc-wcx-hero__copy" in hero and "rmc_info_tag" not in hero:
        return _fail("world_class_page_hero must move subtitle into info tags")
    if "rmc_info_tag" not in hero:
        return _fail("world_class_page_hero missing rmc_info_tag")

    ops = (ROOT / "templates/components/rmc_operational_center_frame.html").read_text(
        encoding="utf-8"
    )
    if "center_purpose" in ops and "rmc_info_tag" not in ops:
        return _fail("operational center frame must park purpose in info tags")

    section = (ROOT / "templates/components/world_class_visual_section_header.html").read_text(
        encoding="utf-8"
    )
    if "rmc_info_tag" not in section:
        return _fail("visual section header must use info tags for purpose")

    flight = (ROOT / "templates/platform_runtime/workflow_flight_deck.html").read_text(
        encoding="utf-8"
    )
    if "Live mission control for platform workflows" in flight and "<p class=\"text-muted" in flight:
        return _fail("flight deck still shows manifesto lede paragraph")
    if "rmc_info_tag" not in flight:
        return _fail("flight deck must use info tag for education")

    catalog = (ROOT / "templates/marketplace/tenant_app_catalog.html").read_text(
        encoding="utf-8"
    )
    if 'id="section-install-flow"' not in catalog or "<details" not in catalog:
        return _fail("marketplace install-flow manifesto must be collapsed details")
    # Ensure the install-flow section itself is a details element
    idx = catalog.find('id="section-install-flow"')
    window = catalog[max(0, idx - 120) : idx + 40]
    if "<details" not in window:
        return _fail("marketplace install-flow manifesto must be collapsed details")

    # Intrusive residual: educational rmc-lede walls must be tip/details, not open prose.
    # Allowed: alert/warn + live-data shells (JS-filled / status counts).
    import re

    lede_re = re.compile(
        r"<p\b([^>]*\bclass=[\"'][^\"']*\brmc-lede\b[^\"']*[\"'][^>]*)>(.*?)</p>",
        re.S | re.I,
    )
    edu_ledes: list[str] = []
    for path in sorted((ROOT / "templates").rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in lede_re.finditer(text):
            attrs = m.group(1)
            if "rmc-lede--warn" in attrs or 'role="alert"' in attrs:
                continue
            if "data-mc-preview" in attrs or "data-rmc-dlq-row-count" in attrs:
                continue
            edu_ledes.append(str(path.relative_to(ROOT)))
    if edu_ledes:
        sample = ", ".join(edu_ledes[:8])
        more = f" (+{len(edu_ledes) - 8} more)" if len(edu_ledes) > 8 else ""
        return _fail(f"educational rmc-lede walls remain: {sample}{more}")

    # Shared hero/setup ledes must not remain as open walls when info tags are the contract.
    setup = (ROOT / "templates/partials/tenant/setup_command_surface.html").read_text(
        encoding="utf-8"
    )
    if "rmc-setup-surface__lede" in setup and "rmc_info_tag" not in setup:
        return _fail("setup command surface still uses open lede without info tag")
    if "rmc_info_tag" not in setup:
        return _fail("setup command surface missing rmc_info_tag")

    console = (ROOT / "templates/migration_cloud/_console_body.html").read_text(
        encoding="utf-8"
    )
    if "rmc_info_tag" not in console:
        return _fail("migration cloud console must educate via rmc_info_tag")
    if re.search(r'<p\b[^>]*\brmc-lede\b', console):
        return _fail("migration cloud console still has open rmc-lede")

    print("CORE_CONTEXT_INFO_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
