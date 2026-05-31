#!/usr/bin/env python3
"""Platform configurability gate — SOT, page-data, migrated JS must use platform surface."""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

SHELLS = (
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/base.html",
    "templates/admin/base_site.html",
)

FORBIDDEN_PORTAL_HYDRATE = re.compile(
    r'["\']/api/entities/students/["\']|["\']/api/attendance/["\']'
)

MIGRATED_JS = (
    "static/js/authenticated-shell-manager.js",
    "static/js/portal-shell-bootstrap.js",
    "static/js/rmc-friction.js",
    "static/js/rmc-iam-snapshot-cache.js",
    "static/js/rmc-admissions-intake.js",
    "static/js/offline-status-bar.js",
    "static/js/theme-preference-bootstrap.js",
    "static/js/rmc-crdt-client.js",
    "static/js/teacher-crossmodule-hover.js",
    "static/js/sentry-browser-bridge.js",
    "static/js/portal-sidebar.js",
    "static/js/auto-pilot.js",
    "static/js/entity-orchestrator.js",
    "static/js/sync-manager.js",
    "static/js/react-hooks.js",
    "static/js/rmc-wizard-state-cache.js",
    "static/js/rmc-lan-mule-sync.js",
    "static/js/rmc-campus-switcher.js",
    "static/js/migration-job-poll.js",
    "static/js/_pages/components__toast_notifications-1.js",
    "static/js/_pages/control_plane_base-1.js",
    "static/js/_pages/components__pin_to_quick_access-1.js",
    "static/js/_pages/accounts__entity_import.js",
    "static/js/_pages/rmc-signup-country-adapter.js",
    "static/js/_pages/customersuccess__guided_onboarding.js",
    "static/js/_pages/backend_base-1.js",
    "static/js/_pages/emis__dashboard-1.js",
    "static/js/rmc-assist-dock.js",
    "static/js/_pages/rmc-ai-stream-bridge.js",
    "static/js/dashboard-layout.js",
    "static/js/_pages/accounts__notifications-1.js",
    "static/js/_pages/observability__platform_incidents.js",
)

FORBIDDEN_ASSIST_DOCK = re.compile(r"""fetch\s*\(\s*['"]/assist-dock/""")
FORBIDDEN_AI_STREAM = re.compile(r"""fetch\s*\(\s*['"]/portal/ai/stream/""")
FORBIDDEN_EMIS_API = re.compile(r"""fetch\s*\(\s*['"]/emis/api/""")

# Infrastructure: path-prefix routing / last-resort CSRF fallback only.
SW_ALLOWED = re.compile(
    r"OFFLINE_CONFIG\.csrfTokenUrl|pathname\.startsWith\(|path\.startsWith\("
)

FORBIDDEN_FETCH = re.compile(r"""fetch\s*\(\s*['"]/api/""")
FORBIDDEN_BEACON = re.compile(r"""sendBeacon\s*\(\s*['"]/api/""")

REQUIRED_MARKERS = (
    (ROOT / "apps/siteconfig/platform_surface_config.py", "platform_client_urls"),
    (ROOT / "apps/siteconfig/platform_surface_config.py", "wizard_cache_telemetry"),
    (ROOT / "apps/setup_studio/views_wizard_cache_telemetry.py", "emit_state_cache_event"),
    (ROOT / "apps/assist_dock/client_urls.py", "resolve_assist_dock_client_urls"),
    (ROOT / "apps/portal/ai_chrome_config.py", "ai_stream"),
    (ROOT / "scripts/scan_hardcoded_client_fetch_paths.py", "HARDCODED_CLIENT_FETCH"),
    (ROOT / "scripts/verify_client_config_cascade.py", "CLIENT_CONFIG_CASCADE"),
    (ROOT / "templates/partials/rmc_platform_surface_page_data.html", "rmc-platform-surface-reader.js"),
    (ROOT / "static/js/rmc-platform-surface-reader.js", "RMCPlatformSurface"),
    (ROOT / "config/settings.py", "platform_surface_settings"),
)


def _read(rel: str) -> str:
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main() -> int:
    findings: list[str] = []

    for path, needle in REQUIRED_MARKERS:
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        if needle not in text:
            findings.append(f"{path.relative_to(ROOT)}: missing '{needle}'")

    portal = _read("templates/portal_base.html")
    if FORBIDDEN_PORTAL_HYDRATE.search(portal):
        findings.append("portal_base.html: hardcoded offline hydrate API paths")
    if "rmc_sms_offline_config.html" not in portal:
        findings.append("portal_base.html: must include rmc_sms_offline_config partial")

    for shell in SHELLS:
        if "rmc_platform_surface_page_data.html" not in _read(shell):
            findings.append(f"{shell}: missing platform surface page-data include")

    for shell in (
        "templates/portal_base.html",
        "templates/control_plane_skeleton.html",
        "templates/admin/base_site.html",
    ):
        text = _read(shell)
        if "rmc-assist-dock.js" in text and "rmc_assist_dock_labels.html" not in text:
            findings.append(f"{shell}: loads assist dock JS without labels page-data partial")

    for shell in (
        "templates/portal_base.html",
        "templates/control_plane_skeleton.html",
        "templates/base.html",
        "templates/admin/base_site.html",
    ):
        text = _read(shell)
        if "rmc_viewport_engine.html" in text and "rmc_ai_chrome_page_data.html" not in text:
            findings.append(
                f"{shell}: viewport engine without ai chrome page-data (stream bridge)"
            )

    for rel in MIGRATED_JS:
        text = _read(rel)
        if not text:
            findings.append(f"{rel}: missing file")
            continue
        if FORBIDDEN_FETCH.search(text) or FORBIDDEN_BEACON.search(text):
            findings.append(f"{rel}: hardcoded /api/ fetch — use RMCPlatformSurface.url")
        if rel == "static/js/rmc-assist-dock.js":
            if FORBIDDEN_ASSIST_DOCK.search(text):
                findings.append(f"{rel}: hardcoded /assist-dock/ fetch — use dockUrl()")
            if "dockUrl" not in text:
                findings.append(f"{rel}: must use dockUrl() for assist-dock endpoints")
            continue
        if rel == "static/js/_pages/rmc-ai-stream-bridge.js":
            if FORBIDDEN_AI_STREAM.search(text):
                findings.append(f"{rel}: hardcoded /portal/ai/stream/ — use page-data-rmc-ai-chrome")
            if "page-data-rmc-ai-chrome" not in text:
                findings.append(f"{rel}: must read ai_stream from page-data-rmc-ai-chrome")
            continue
        if rel in (
            "static/js/dashboard-layout.js",
            "static/js/_pages/accounts__notifications-1.js",
            "static/js/_pages/observability__platform_incidents.js",
        ):
            if FORBIDDEN_FETCH.search(text):
                findings.append(f"{rel}: hardcoded /api/ fetch — use RMCPlatformSurface")
            if "RMCPlatformSurface" not in text:
                findings.append(f"{rel}: must reference RMCPlatformSurface")
            continue
        if rel == "static/js/_pages/emis__dashboard-1.js":
            if FORBIDDEN_EMIS_API.search(text):
                findings.append(f"{rel}: hardcoded /emis/api/ fetch — use page-data URLs")
            if "__RMC_PAGE_DATA__" not in text:
                findings.append(f"{rel}: must read EMIS URLs from page-data")
            continue
        if "RMCPlatformSurface" not in text and "rmcEntityUrl" not in text:
            findings.append(f"{rel}: must reference RMCPlatformSurface")

    sw = _read("static/js/service-worker.js")
    if FORBIDDEN_FETCH.search(sw) and not SW_ALLOWED.search(sw):
        findings.append("service-worker.js: hardcoded fetch('/api/') without OFFLINE_CONFIG.csrfTokenUrl")

    cmdk = _read("templates/components/rmc_command_palette.html")
    if "/api/v1/ai/line-interpret/" in cmdk:
        findings.append("rmc_command_palette.html: hardcoded ai line-interpret path")

    for tpl in ("templates/components/rmc_campus_switcher.html",):
        if 'data-schools-url="/api/v1/me/schools"' in _read(tpl):
            findings.append(f"{tpl}: hardcoded me/schools path")

    for tpl in ("templates/super/wedges/index.html", "templates/super/wedges/detail.html"):
        if "/api/v1/super/wedges/" in _read(tpl):
            findings.append(f"{tpl}: hardcoded wedge API path")

    cp = _read("apps/assist_dock/context_processors.py")
    if "filter_assist_dock_slots" not in cp:
        findings.append("assist_dock: feature-flag filter not wired")

    if findings:
        for item in findings:
            print(f"FAIL: {item}")
        print(f"\nPLATFORM_CONFIG_CASCADE_FAIL ({len(findings)} findings)")
        return 1

    print("PLATFORM_CONFIG_CASCADE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
