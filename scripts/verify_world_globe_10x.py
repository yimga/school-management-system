#!/usr/bin/env python3
"""Verify Global Footprint 10x phases A–E (batch 1653).

Exit 0 + WORLD_GLOBE_10X_PASS when hero layout, bridge, API, and mount API ship.
"""
from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser()
    parser.parse_args()

    tpl = (ROOT / "templates/partials/cockpit/_live_world_map.html").read_text(encoding="utf-8")
    for marker in (
        "lx-world--{{ lwm_layout }}",
        "lx-world__globe-skeleton",
        "data-rmc-region",
        "data-rmc-status-filter",
        "rmc-world-globe-bridge.js",
        "rmc-world-globe-school-sheet",
        "rmc-world-globe-freshness",
        "rmc-world-globe-wow-plus.js",
        "rmc-world-globe-celebrate",
        "lx-world__void-zone--share",
    ):
        if marker not in tpl:
            _fail(f"template missing 10x marker {marker!r}")

    css = (ROOT / "static/css/rmc-cp-200x.css").read_text(encoding="utf-8")
    for rule in (".lx-world--hero", ".lx-world__legend-panel", ".lx-world__freshness"):
        if rule not in css:
            _fail(f"rmc-cp-200x.css missing {rule}")

    bridge = ROOT / "static/js/rmc-world-globe-bridge.js"
    if not bridge.is_file() or bridge.stat().st_size < 500:
        _fail("rmc-world-globe-bridge.js missing or too small")

    mount = (ROOT / "src/apps/worldGlobe/mount.ts").read_text(encoding="utf-8")
    for token in ("RMCWorldGlobe", "flyToRegion", "startTour", "arcsData", "refreshLive", "refreshMarkers", "labelsData", "region_labels", "setWowMode", "expansion_targets"):
        if token not in mount:
            _fail(f"mount.ts missing 10x token {token!r}")

    geo = (ROOT / "apps/siteconfig/world_map_geo.py").read_text(encoding="utf-8")
    for token in ("build_globe_live_bundle", "compute_globe_revision", "live_refresh", "compute_default_camera", "GLOBE_FILL_ALTITUDE"):
        if token not in geo:
            _fail(f"world_map_geo.py missing {token!r}")

    if "rmc-operator-fleet-bootstrap" not in tpl:
        _fail("template missing SSR fleet bootstrap embed")

    urls = (ROOT / "apps/schools/super_urls.py").read_text(encoding="utf-8")
    if "api/globe/markers/" not in urls or "api/globe/stream/" not in urls or "api/globe/live/" not in urls:
        _fail("super_urls missing globe API routes")

    views = (ROOT / "apps/siteconfig/views_globe_api.py").read_text(encoding="utf-8")
    if "api/globe/live/" not in urls or "globe_live_api" not in views:
        _fail("globe live API route or view missing")
    for token in ("globe_markers_api", "GlobeStreamView"):
        if token not in views:
            _fail(f"views_globe_api missing {token!r}")

    forms = (ROOT / "apps/siteconfig/forms_cockpit.py").read_text(encoding="utf-8")
    if "lwm_layout" not in forms or "lwm_tour_enabled" not in forms:
        _fail("forms_cockpit missing layout/tour operator fields")

    if "def build_globe_payload" not in geo or "region_centroids" not in geo:
        _fail("build_globe_payload missing region_centroids wiring")

    _ok("WORLD_GLOBE_10X_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
