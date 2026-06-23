#!/usr/bin/env python3
"""Verify globe void/AI lab W1–W20 + tier-1 parity ships in production templates/JS/CSS/API."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WOW_MARKERS: dict[str, tuple[str, ...]] = {
    "W1": ("lx-world__globe--revealed", "lx-world-globe-reveal"),
    "W2": ("arcDashAnimateTime", "arcsData"),
    "W3": ("lx-world__map--aurora-warn", "applyAurora"),
    "W4": ("ringsData", "syncPulseRings"),
    "W5": ("lx-world__count--bump",),
    "W6": ("lx-world__terminator", "wireDayNightTerminator", "day_night_terminator"),
    "W7": ("lx-world__globe-tip", "pointLabel"),
    "W8": ("rmc-world-globe-share-viewport", "wireShareViewport"),
    "W9": ("wireTourControls", 'ev.key === "t"'),
    "W10": ("first_visit_fly_in", "maybeFirstVisitFlyIn", "rmc-globe-first-visit-done"),
    "W11": ("cluster_bloom", "clusterBloomRadius", "is_cluster"),
    "W12": ("tour_narrator", "wireTourNarrator", "operator_fleet_tour_narrator"),
    "W13": ("wireVoidParallax", "void_parallax"),
    "W14": ("buildGoldenTourArcs", "startTour"),
    "W15": ("suspended", "ringMaxRadius"),
    "W16": ("showRegionalDeltas", "lx-world__delta-badge"),
    "W17": ("globe_presence", "sendGlobePresenceHeartbeat"),
    "W18": ("wireVoidParallax",),
    "W19": ("maybeCelebrateOnboard", "lx-world__celebrate"),
    "W20": ("exportExecutiveSnapshot", "rmc-world-globe-snapshot-export"),
}

VOID_TIER = (
    "rmc-world-globe-void-viewport",
    "rmc-world-globe-void-whisper",
    "rmc-world-globe-void-caption",
    "rmc-world-globe-fleet-pulse",
    "rmc-world-globe-ai-brief",
    "rmc-operator-fleet-bus",
)


def _fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _read(*parts: str) -> str:
    return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    tpl = _read("templates/partials/cockpit/_live_world_map.html")
    bridge = _read("static/js/rmc-world-globe-bridge.js")
    wow_plus = _read("static/js/rmc-world-globe-wow-plus.js")
    mount = _read("src/apps/worldGlobe/mount.ts")
    css = _read("static/css/rmc-cp-200x.css")
    geo = _read("apps/siteconfig/world_map_geo.py")
    fleet_svc = _read("apps/siteconfig/fleet_context_service.py")
    fleet_api = _read("apps/siteconfig/views_operator_fleet_api.py")
    urls = _read("apps/schools/super_urls.py")
    skeleton = _read("templates/control_plane_skeleton.html")

    for marker in VOID_TIER:
        if marker == "rmc-operator-fleet-bus":
            if marker not in skeleton:
                _fail(f"control_plane_skeleton missing {marker!r}")
        elif marker not in tpl:
            _fail(f"_live_world_map.html missing void/fleet marker {marker!r}")

    for wow_id, tokens in WOW_MARKERS.items():
        haystacks = (tpl, bridge, wow_plus, mount, css, geo, fleet_svc, fleet_api, urls)
        if not any(any(tok in h for tok in tokens) for h in haystacks):
            _fail(f"{wow_id} missing all tokens {tokens!r}")

    for feat in (
        "void_zones",
        "fleet_pulse",
        "ai_whisper",
        "ai_brief",
        "day_night_terminator",
        "tour_narrator",
        "first_visit_fly_in",
        "cluster_bloom",
    ):
        if f'"{feat}": True' not in geo:
            _fail(f"world_map_geo features missing {feat!r}")

    if "api/operator/fleet/tour-narrator/" not in urls:
        _fail("super_urls missing tour-narrator route")
    if "build_tour_narrator_line" not in fleet_svc:
        _fail("fleet_context_service missing build_tour_narrator_line")
    if "operator_fleet_tour_narrator_api" not in fleet_api:
        _fail("views_operator_fleet_api missing tour narrator view")

    print("GLOBE_VOID_AI_LAB_PARITY_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
