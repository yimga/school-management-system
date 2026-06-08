#!/usr/bin/env python3
"""Integration gate: Global Footprint + glocal shell + offline/local-first + KB/LibreOffice.

Batch 1650 — ensures operator globe, tenant offline stack, regional UI, and KB
offline pack are wired together for seamless online/offline experience.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    findings: list[str] = []

    globe_tpl = _text("templates/partials/cockpit/_live_world_map.html")
    loader = _text("static/js/rmc-world-globe-loader.js")
    if "data-rmc-offline-surface" not in globe_tpl:
        findings.append("globe template missing data-rmc-offline-surface")
    if "rmc-world-globe-offline-note" not in globe_tpl:
        findings.append("globe template missing offline notice")
    if "shouldSkipHeavyGlobe" not in loader or "markOfflineFallback" not in loader:
        findings.append("globe loader missing offline/low-bandwidth guards")
    if "isNavigatorOffline" not in loader or "ensureSvgVisible" not in loader:
        findings.append("globe loader missing offline blank-screen guards")
    if "rmc-world-globe-bridge.js" not in globe_tpl:
        findings.append("globe template missing rmc-world-globe-bridge.js")
    if "data-rmc-region" not in globe_tpl:
        findings.append("globe template missing legend region fly-to hooks")

    sw = _text("static/js/service-worker.js")
    for asset in (
        "rmc-world-globe-loader.js",
        "rmc-world-globe-bridge.js",
        "world-globe.mount.js",
        "world-countries-110m.json",
        "earth-night-1k.jpg",
    ):
        if asset not in sw:
            findings.append(f"service-worker missing precache for {asset}")

    psc = _text("apps/siteconfig/platform_surface_config.py")
    if "kb_offline_pack" not in psc or "operatorControlPlaneShell" not in psc:
        findings.append("platform_surface_config missing KB offline + operator shell flags")
    if "kb_articles" not in psc or "kb_article" not in psc:
        findings.append("platform_surface_config missing kb_articles hydrate endpoint")

    portal = _text("templates/portal_base.html")
    cp = _text("templates/control_plane_skeleton.html")
    if "rmc_sms_offline_config.html" not in portal:
        findings.append("portal_base missing SMS offline config partial")
    if "regional-rtl.css" not in portal or "glocal-text-expansion.css" not in portal:
        findings.append("portal_base missing glocal regional CSS")
    if "rmc-kb-offline-cache.js" not in portal:
        findings.append("portal_base missing KB offline cache script")
    if "rmc-service-worker-registration.js" not in cp:
        findings.append("control_plane_skeleton missing service worker registration")
    if "data-rmc-low-bandwidth" not in cp and "data-rmc-low-bandwidth" not in portal:
        findings.append("shells missing low-bandwidth attribute contract")

    offline_db = _text("static/js/offline-db.js")
    if "kb_articles" not in offline_db or "kb_article" not in offline_db:
        findings.append("offline-db missing kb_articles store/normalizer")

    kb_offline = ROOT / "apps/portal/views_kb_offline.py"
    if not kb_offline.is_file():
        findings.append("missing apps/portal/views_kb_offline.py")
    elif "api_kb_offline_pack" not in kb_offline.read_text(encoding="utf-8"):
        findings.append("views_kb_offline missing api_kb_offline_pack")

    reimport = _text("templates/portal/partials/kb_article_staff_reimport.html")
    if 'data-rmc-offline-form="field_capture"' not in reimport:
        findings.append("KB ODT reimport form missing offline field_capture marker")

    prefetch = _text("apps/api/offline_replay_views.py")
    if "kb/offline-pack" not in prefetch:
        findings.append("PrefetchUrlsAPI missing KB offline pack URL")
    if "world-globe" not in prefetch and "rmc-world-globe-loader" not in prefetch:
        findings.append("PrefetchUrlsAPI missing globe static assets for operators")

    sw_reg = _text("static/js/rmc-service-worker-registration.js")
    if "operatorControlPlaneShell" not in sw_reg:
        findings.append("SW registration missing operatorControlPlaneShell gate")

    if not (ROOT / "static/js/rmc-kb-offline-cache.js").is_file():
        findings.append("missing static/js/rmc-kb-offline-cache.js")

    if findings:
        print("verify_global_footprint_glocal_offline_integration: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("GLOBAL_FOOTPRINT_GLOCAL_OFFLINE_INTEGRATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
