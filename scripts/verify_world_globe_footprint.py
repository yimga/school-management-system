#!/usr/bin/env python3
"""Verify Global Footprint interactive globe wiring (batch 1645 + 1650 offline integration).

Checks template mount, static bundle, geo asset, resolver payload shape, and
status colour contract alignment. Exit 0 + WORLD_GLOBE_FOOTPRINT_PASS on clean tree.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_MARKERS = (
    "id=\"rmc-world-globe\"",
    "id=\"rmc-world-globe-stage\"",
    "id=\"rmc-world-globe-data\"",
    "data-rmc-schools-list-url",
    "rmc-world-globe-loader.js",
    "globe_payload_json",
)
STATUS_HEX = ("#6ee7b7", "#fcd34d", "#93c5fd")


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(msg)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    template = ROOT / "templates/partials/cockpit/_live_world_map.html"
    if not template.is_file():
        _fail(f"missing template {template}")

    tpl = template.read_text(encoding="utf-8")
    for marker in REQUIRED_MARKERS:
        if marker not in tpl:
            _fail(f"template missing {marker!r}")

    bundle = ROOT / "static/js/dist/world-globe.mount.js"
    if not bundle.is_file() or bundle.stat().st_size < 500_000:
        _fail("world-globe.mount.js missing or too small — run npm run build:world-globe (single-file bundle)")
    head = bundle.read_text(encoding="utf-8", errors="replace")[:800]
    if "./world-globe.vendor-" in head:
        _fail("world-globe.mount.js must be a single-file bundle (no relative vendor chunk imports)")

    dist = ROOT / "static/js/dist"
    if dist.is_dir():
        stale = [p.name for p in dist.iterdir() if p.is_file() and p.name.startswith("world-globe.vendor-")]
        if stale:
            _fail(f"retired vendor chunks in static/js/dist: {', '.join(stale)}")

    loader = ROOT / "static/js/rmc-world-globe-loader.js"
    if not loader.is_file() or loader.stat().st_size < 100:
        _fail("static/js/rmc-world-globe-loader.js missing")

    geo = ROOT / "static/geo/world-countries-110m.json"
    if not geo.is_file():
        _fail("static/geo/world-countries-110m.json missing")
    texture = ROOT / "static/img/globe/earth-night-1k.jpg"
    if not texture.is_file() or texture.stat().st_size < 5_000:
        _fail("static/img/globe/earth-night-1k.jpg missing — run python scripts/generate_globe_earth_night_texture.py")
    try:
        geo_data = json.loads(geo.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _fail(f"invalid geo json: {exc}")
    if not geo_data.get("features"):
        _fail("geo json has no features")

    geo_py = ROOT / "apps/siteconfig/world_map_geo.py"
    src = geo_py.read_text(encoding="utf-8")
    ast.parse(src)
    if "GLOBE_EARTH_TEXTURE_URL" not in src or "globe_texture_url" not in src:
        _fail("world_map_geo.py missing globe_texture_url wiring")
    for hx in STATUS_HEX:
        if hx not in src:
            _fail(f"world_map_geo.py missing status colour {hx}")

    svc = (ROOT / "apps/siteconfig/cockpit_panels_realdata_service.py").read_text(encoding="utf-8")
    if "globe_payload_json" not in svc or "_world_map_globe_payload" not in svc:
        _fail("cockpit_panels_realdata_service missing globe payload wiring")
    if '"settings"' not in svc or "_resolve_school_coords" not in (ROOT / "apps/siteconfig/world_map_geo.py").read_text(encoding="utf-8"):
        _fail("world map geo resolver missing settings.location precision path")

    forms = (ROOT / "apps/siteconfig/forms_cockpit.py").read_text(encoding="utf-8")
    if "lwm_globe_auto_rotate" not in forms or "globe_auto_rotate" not in forms:
        _fail("forms_cockpit missing lwm_globe_auto_rotate operator toggle")

    css = (ROOT / "static/css/rmc-cp-200x.css").read_text(encoding="utf-8")
    if ".lx-world__globe" not in css:
        _fail("rmc-cp-200x.css missing .lx-world__globe rules")
    if ".lx-world__svg-land" not in css or "fill:" not in css.split(".lx-world__svg-land")[1][:200]:
        _fail("rmc-cp-200x.css missing default .lx-world__svg-land fill (offline blank guard)")
    if "data-rmc-globe-mode=\"svg-offline\"" not in css and "data-rmc-globe-mode='svg-offline'" not in css:
        _fail("rmc-cp-200x.css missing svg-offline display guard for offline SVG")

    e2e = (ROOT / "tests/e2e/control-plane-layout-audit.spec.js").read_text(encoding="utf-8")
    if "lx-world__globe" not in e2e and "lx-world__svg-fallback" not in e2e:
        _fail("control-plane layout audit not updated for globe")

    mount_ts = (ROOT / "src/apps/worldGlobe/mount.ts").read_text(encoding="utf-8")
    if not re.search(r"Globe\(\)\(", mount_ts):
        _fail("mount.ts must invoke Globe()(container)")
    if "country_code" not in mount_ts or "rmc:globe-marker-click" not in mount_ts:
        _fail("mount.ts missing marker click event contract")

    loader = (ROOT / "static/js/rmc-world-globe-loader.js").read_text(encoding="utf-8")
    if "shouldSkipHeavyGlobe" not in loader:
        _fail("rmc-world-globe-loader.js missing offline/low-bandwidth skip guard")
    if "type = \"module\"" not in loader and "tag.type = \"module\"" not in loader:
        _fail("globe loader must load mount bundle as ES module")

    if "data-rmc-offline-surface" not in tpl:
        _fail("template missing data-rmc-offline-surface on globe mount")

    if "rmc-world-globe-bridge.js" not in tpl:
        _fail("template missing rmc-world-globe-bridge.js")

    mount_ts = (ROOT / "src/apps/worldGlobe/mount.ts").read_text(encoding="utf-8")
    if "RMCWorldGlobe" not in mount_ts:
        _fail("mount.ts must export window.RMCWorldGlobe API")

    defaults = (ROOT / "apps/siteconfig/cockpit_manager_200x.py").read_text(encoding="utf-8")
    if "globe_payload_json" not in defaults or "globe_auto_rotate" not in defaults:
        _fail("cockpit_manager_200x defaults missing globe bootstrap keys")

    _ok("WORLD_GLOBE_FOOTPRINT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
