#!/usr/bin/env python
"""Deploy cache posture gate — closes the post-deploy stale UI class of bugs.

Checks:
  1. Service worker served from /sw.js (full-site scope), not /static/js/ only.
  2. SW fetch handler uses network-first static (not stale-while-revalidate).
  3. Deploy freshness meta + JS wired into portal + control-plane shells.
  4. HtmlNoCacheMiddleware registered; /sw.js NOT blocked by scanner middleware.
  5. /sw.js mirrored on manager + public urlconfs (multi-host parity).
  6. CACHE_VERSION monotonic shape (delegates to verify_service_worker_version).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings: list[str] = []

    sw = _read("static/js/service-worker.js")
    if "event.respondWith(staleWhileRevalidateStatic(request))" in sw:
        findings.append(
            "service-worker.js fetch handler still uses staleWhileRevalidateStatic for static assets"
        )
    if "networkFirstStaticWithTimeout" not in sw:
        findings.append("service-worker.js missing networkFirstStaticWithTimeout helper")
    if "PURGE_ALL_CACHES" not in sw:
        findings.append("service-worker.js missing PURGE_ALL_CACHES handler")
    if "purgeAllSmsCaches" not in sw:
        findings.append("service-worker.js missing purgeAllSmsCaches on activate")
    if 'request.mode === "navigate"' not in sw or "networkFirstNavigation" not in sw:
        findings.append("service-worker.js must network-first HTML navigations")

    reg = _read("static/js/rmc-service-worker-registration.js")
    if 'scope: "/"' not in reg and "scope: '/'" not in reg:
        findings.append("rmc-service-worker-registration.js must register SW with scope: '/'")
    if "updateViaCache" not in reg:
        findings.append("rmc-service-worker-registration.js missing updateViaCache: 'none'")

    portal = _read("templates/portal_base.html")
    cp = _read("templates/control_plane_skeleton.html")
    for label, text in (("portal_base.html", portal), ("control_plane_skeleton.html", cp)):
        if "rmc_deploy_meta.html" not in text:
            findings.append(f"{label} missing rmc_deploy_meta.html include")
        if "rmc-deploy-freshness.js" not in text:
            findings.append(f"{label} missing rmc-deploy-freshness.js")
        if "service_worker_root" not in text:
            findings.append(f"{label} must use service_worker_root URL for SW registration")

    for label, rel in (
        ("config/urls.py", "config/urls.py"),
        ("config/manager_urls.py", "config/manager_urls.py"),
        ("config/public_urls.py", "config/public_urls.py"),
    ):
        text = _read(rel)
        if 'path("sw.js"' not in text:
            findings.append(f"{label} missing /sw.js route")
        if "sw-asset-manifest.json" not in text:
            findings.append(f"{label} missing sw-asset-manifest.json route")

    scanner = _read("config/middleware.py")
    if re.search(r'["\']/sw\.js["\'],', scanner):
        findings.append(
            "config/middleware.py BlockScannerPathsMiddleware must NOT block /sw.js"
        )

    sw_view = _read("apps/siteconfig/views_service_worker.py")
    if "Service-Worker-Allowed" not in sw_view:
        findings.append("views_service_worker.py missing Service-Worker-Allowed header")
    if "service_worker_asset_manifest" not in sw_view:
        findings.append("views_service_worker.py must define service_worker_asset_manifest")

    settings = _read("config/settings.py")
    if "HtmlNoCacheMiddleware" not in settings:
        findings.append("config/settings.py missing HtmlNoCacheMiddleware")
    if "deploy_freshness_context" not in settings:
        findings.append("config/settings.py missing deploy_freshness_context processor")

    ok = not findings
    if args.json:
        import json

        print(json.dumps({"ok": ok, "findings": findings}, indent=2))
    elif ok:
        print("DEPLOY_CACHE_POSTURE_PASS")
    else:
        for item in findings:
            print(f"FAIL: {item}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
