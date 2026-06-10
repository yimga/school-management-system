"""
Verify platform fleet monitoring contract — heatmap, pulse, live APIs, SSE, exports.

Exit 0 with PLATFORM_FLEET_MONITORING_PASS when all checks pass.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "apps/schools/fleet_status.py",
    "apps/schools/fleet_live_payload.py",
    "apps/schools/fleet_report_markdown.py",
    "apps/schools/tenant_operational_health.py",
    "apps/schools/views_fleet_live.py",
    "apps/schools/views_tenant_health_api.py",
    "apps/siteconfig/views_cockpit_live.py",
    "static/js/rmc-cp-cockpit-live.js",
    "static/js/rmc-fleet-live.js",
    "static/js/rmc-tenant-health-live.js",
    "templates/partials/cockpit/_tenant_heatmap.html",
    "templates/partials/tenant/operational_health_strip.html",
    "templates/schools/super_tenant_health.html",
)

REQUIRED_SYMBOLS = {
    "apps/schools/fleet_status.py": (
        "resolve_fleet_summary",
        "resolve_fleet_tiles",
        "resolve_school_fleet_status",
        "format_fleet_summary_label",
    ),
    "apps/schools/fleet_live_payload.py": (
        "build_fleet_live_payload",
        "build_fleet_sse_payload",
    ),
    "apps/schools/fleet_report_markdown.py": ("build_fleet_status_markdown",),
    "apps/schools/tenant_operational_health.py": ("resolve_tenant_operational_health",),
    "apps/siteconfig/views_cockpit_live.py": ("cockpit_live_json",),
    "apps/schools/views_fleet_live.py": ("fleet_live_json", "FleetStreamView"),
    "apps/schools/views_tenant_health_api.py": (
        "tenant_operational_health_json",
        "TenantHealthStreamView",
        "build_tenant_health_payload",
    ),
}

FORBIDDEN_PATTERNS = {
    "static/js/rmc-cp-cockpit-live.js": (
        r"127\.0\.0\.1:7426",
        r"debug-a48ae2",
    ),
    "apps/siteconfig/views_cockpit_live.py": (
        r"debug-a48ae2",
        r"_agent_debug_log",
    ),
}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _check_paths() -> list[str]:
    errors: list[str] = []
    for rel in REQUIRED_PATHS:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")
    return errors


def _check_symbols() -> list[str]:
    errors: list[str] = []
    for rel, names in REQUIRED_SYMBOLS.items():
        text = _read(rel)
        tree = ast.parse(text)
        defined = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        for name in names:
            if name not in defined:
                errors.append(f"{rel}: missing symbol {name}")
    return errors


def _check_forbidden() -> list[str]:
    errors: list[str] = []
    for rel, patterns in FORBIDDEN_PATTERNS.items():
        text = _read(rel)
        for pat in patterns:
            if re.search(pat, text):
                errors.append(f"{rel}: forbidden pattern {pat}")
    return errors


def _check_urls() -> list[str]:
    errors: list[str] = []
    urls = _read("apps/schools/super_urls.py")
    accounts_urls = _read("apps/accounts/urls.py")
    portal_urls = _read("apps/portal/urls.py")
    for needle in (
        "api/fleet/live.json",
        "api/fleet/stream/",
        "export/fleet-status.odt",
        "api_cockpit_live",
    ):
        if needle not in urls:
            errors.append(f"super_urls.py: missing route fragment {needle}")
    if "backend/api/operational-health.json" not in accounts_urls:
        errors.append("accounts/urls.py: missing tenant operational health JSON route")
    if "backend/api/operational-health/stream/" not in accounts_urls:
        errors.append("accounts/urls.py: missing tenant operational health SSE route")
    if "api/operational-health.json" not in portal_urls:
        errors.append("portal/urls.py: missing portal operational health JSON route")
    if "api/operational-health/stream/" not in portal_urls:
        errors.append("portal/urls.py: missing portal operational health SSE route")
    return errors


def _check_wiring() -> list[str]:
    errors: list[str] = []
    heatmap_resolver = _read("apps/siteconfig/cockpit_panels_realdata_service.py")
    if "resolve_fleet_tiles" not in heatmap_resolver:
        errors.append("cockpit_panels_realdata_service: heatmap must use resolve_fleet_tiles")
    pulse = _read("apps/siteconfig/cockpit_platform_pulse_service.py")
    if "resolve_fleet_summary" not in pulse:
        errors.append("cockpit_platform_pulse_service: schools card must use resolve_fleet_summary")
    fleet_js = _read("static/js/rmc-fleet-live.js")
    if "EventSource" not in fleet_js:
        errors.append("rmc-fleet-live.js: must use SSE EventSource")
    if "buildStreamEndpoint" not in fleet_js:
        errors.append("rmc-fleet-live.js: must build paginated SSE stream URL")
    if "include_rows=1" not in fleet_js:
        errors.append("rmc-fleet-live.js: must request include_rows on paginated SSE")
    cockpit_js = _read("static/js/rmc-cp-cockpit-live.js")
    if "/super/api/fleet/stream/" not in cockpit_js:
        errors.append("rmc-cp-cockpit-live.js: must subscribe to fleet SSE")
    tenant_js = _read("static/js/rmc-tenant-health-live.js")
    if "EventSource" not in tenant_js:
        errors.append("rmc-tenant-health-live.js: must use SSE EventSource")
    if "operational-health" not in tenant_js and "tenant-health-endpoint" not in tenant_js:
        errors.append("rmc-tenant-health-live.js: must poll tenant health endpoint")
    tenant_health = _read("templates/schools/super_tenant_health.html")
    if 'data-rmc-fleet-live="1"' not in tenant_health:
        errors.append("super_tenant_health.html: missing data-rmc-fleet-live")
    dashboard = _read("templates/schools/super_dashboard.html")
    if 'data-rmc-fleet-live="1"' not in dashboard:
        errors.append("super_dashboard.html: registry must have data-rmc-fleet-live")
    if "export_fleet_status_odt" not in dashboard:
        errors.append("super_dashboard.html: missing ODT export CTA")
    backend = _read("templates/accounts/backend_dashboard.html")
    if "operational_health_strip.html" not in backend:
        errors.append("backend_dashboard.html: missing tenant operational health strip")
    parent_dash = _read("templates/parent/dashboard.html")
    if "operational_health_strip.html" not in parent_dash:
        errors.append("parent/dashboard.html: missing tenant operational health strip")
    if "portal_operational_health_stream" not in parent_dash:
        errors.append("parent/dashboard.html: missing portal operational health SSE URL")
    if "rmc-tenant-health-live.js" not in parent_dash:
        errors.append("parent/dashboard.html: missing rmc-tenant-health-live.js")
    student_home = _read("templates/student/learning_home.html")
    if "operational_health_strip.html" not in student_home:
        errors.append("student/learning_home.html: missing tenant operational health strip")
    if "portal_operational_health_stream" not in student_home:
        errors.append("student/learning_home.html: missing portal operational health SSE URL")
    if "rmc-tenant-health-live.js" not in student_home:
        errors.append("student/learning_home.html: missing rmc-tenant-health-live.js")
    teacher_dash = _read("templates/teacher/dashboard.html")
    if "operational_health_strip.html" not in teacher_dash:
        errors.append("teacher/dashboard.html: missing tenant operational health strip")
    exports = _read("apps/schools/super_views_exports.py")
    if "export_fleet_status_odt" not in exports:
        errors.append("super_views_exports.py: missing ODT export view")
    if "markdown_to_document" not in exports:
        errors.append("super_views_exports.py: ODT must use markdown_to_document")
    stream = _read("apps/schools/views_fleet_live.py")
    if "text/event-stream" not in stream:
        errors.append("views_fleet_live.py: FleetStreamView must emit text/event-stream")
    if "build_fleet_sse_payload" not in stream:
        errors.append("views_fleet_live.py: must use build_fleet_sse_payload")
    tenant_stream = _read("apps/schools/views_tenant_health_api.py")
    if "text/event-stream" not in tenant_stream:
        errors.append("views_tenant_health_api.py: TenantHealthStreamView must emit text/event-stream")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_paths())
    errors.extend(_check_symbols())
    errors.extend(_check_forbidden())
    errors.extend(_check_urls())
    errors.extend(_check_wiring())

    if errors:
        print("PLATFORM_FLEET_MONITORING_FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("PLATFORM_FLEET_MONITORING_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
