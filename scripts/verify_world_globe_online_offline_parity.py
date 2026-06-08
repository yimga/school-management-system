#!/usr/bin/env python3
"""Verify online/offline parity for Global Footprint globe (batch 1654).

Exit 0 + WORLD_GLOBE_ONLINE_OFFLINE_PARITY_PASS when production template, bridge,
loader, mount, and preview artifact share the same labeling + fallback contract.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(msg)


def main() -> int:
    tpl = (ROOT / "templates/partials/cockpit/_live_world_map.html").read_text(encoding="utf-8")
    for marker in (
        "lx-world__svg-region-label",
        "data-rmc-region",
        "lx-world__dot-group",
        "data-rmc-status",
        "data-rmc-country",
        "rmc-world-globe-bridge.js",
        "lx-world__globe-skeleton",
        "rmc-world-globe-stage",
        "lx-world__globe-stage",
    ):
        if marker not in tpl:
            _fail(f"template missing parity marker {marker!r}")

    bridge = (ROOT / "static/js/rmc-world-globe-bridge.js").read_text(encoding="utf-8")
    for token in ("stageEl", "svgRoot", "rmc-world-globe-stage"):
        if token not in bridge:
            _fail(f"bridge missing stage-mount token {token!r}")
    for token in (
        "triggerLiveRefresh",
        "rmc:globe-live-updated",
        "applyLiveChrome",
        "mergeLiveIntoPayload",
        "syncSvgLabelsFromBundle",
        "startPollFallback",
        "applySvgPalette",
        "highlightSvgRegion",
        "wireSvgDots",
        "Offline map",
        "startSvgRegionTour",
        "stopSvgRegionTour",
    ):
        if token not in bridge:
            _fail(f"bridge missing live refresh token {token!r}")

    loader = (ROOT / "static/js/rmc-world-globe-loader.js").read_text(encoding="utf-8")
    if "rmc:globe-offline-fallback" not in loader:
        _fail("loader must dispatch rmc:globe-offline-fallback")
    for token in ("ensureSvgVisible", "isNavigatorOffline", "isSvgOfflineMode", "markOfflineFallback", "removeMountScript", "globeStage"):
        if token not in loader:
            _fail(f"loader missing offline blank-screen token {token!r}")

    mount = (ROOT / "src/apps/worldGlobe/mount.ts").read_text(encoding="utf-8")
    for token in ("getGlobeStage", "rmc-world-globe-stage"):
        if token not in mount:
            _fail(f"mount.ts missing stage-mount token {token!r}")
    for token in ("syncMapLabels", "refreshLive", "applyLiveBundle", "globe_texture_url", "countryLabelOpacity", "labelsData", "region_labels", "country_labels", "region_palette", "ringsData", "iso3_region_map", "country_name", "rmc:globe-offline-fallback", "zoomRefreshTimer", "tour_waypoints", "isSvgOfflineLocked"):
        if token not in mount:
            _fail(f"mount.ts missing parity token {token!r}")

    geo = (ROOT / "apps/siteconfig/world_map_geo.py").read_text(encoding="utf-8")
    for token in ("region_labels", "country_labels", "region_palette", "globe_texture_url", "label_zoom", "lat_lng_to_svg", "iso3_region_map", "SVG_REGION_LABELS", "country_name", "enrich_regional_breakdown"):
        if token not in geo:
            _fail(f"world_map_geo.py missing {token!r}")

    preview = ROOT / "artifacts/global-footprint-section-preview.html"
    if preview.is_file():
        prev = preview.read_text(encoding="utf-8")
        for marker in ("lx-world--hero", "rmc-world-globe-bridge.js", "data-rmc-region", "lx-world__svg-region-label", "lx-world__svg-country-label", "lx-world__svg-land", "data-rmc-country", "api/globe/live/", "live_refresh", "rmc-world-globe-stage"):
            if marker not in prev:
                _fail(f"preview artifact missing parity marker {marker!r}")

    css = (ROOT / "static/css/rmc-cp-200x.css").read_text(encoding="utf-8")
    if ".lx-world__svg-country-label" not in css or ".lx-world__svg-land" not in css:
        _fail("rmc-cp-200x.css missing SVG country label / land styles")

    preview_data = (ROOT / "apps/siteconfig/cockpit_manager_200x_preview_data.py").read_text(encoding="utf-8")
    for token in ("build_globe_markers", "enrich_regional_breakdown", "_world_map_tenant_dots"):
        if token not in preview_data:
            _fail(f"cockpit_manager_200x_preview_data.py missing demo parity token {token!r}")

    forms_cockpit = (ROOT / "apps/siteconfig/forms_cockpit.py").read_text(encoding="utf-8")
    if "enrich_regional_breakdown(lwm_regional)" not in forms_cockpit:
        _fail("forms_cockpit must enrich operator regional rows with SVG label anchors")

    ctx = (ROOT / "apps/siteconfig/cockpit_context.py").read_text(encoding="utf-8")
    if "svg_country_labels" not in ctx:
        _fail("cockpit_context must expose svg_country_labels for offline map")
    if "enrich_regional_breakdown(breakdown)" not in ctx:
        _fail("cockpit_context must enrich regional_breakdown at render time")

    _ok("WORLD_GLOBE_ONLINE_OFFLINE_PARITY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
