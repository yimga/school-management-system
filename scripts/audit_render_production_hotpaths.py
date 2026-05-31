#!/usr/bin/env python3
"""
Static audit for Render production hot-path regressions.

Exits 0 when the tree satisfies known fixes; 1 when actionable drift is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []

    build = _read("build.sh")
    if "gunicorn.real" not in build or "config/gunicorn.conf.py" not in build:
        failures.append("build.sh: missing Gunicorn wrapper install for gunicorn.conf.py")

    gconf = _read("config/gunicorn.conf.py")
    if "gthread" not in gconf:
        failures.append("config/gunicorn.conf.py: worker_class should default to gthread")
    if 'GUNICORN_TIMEOUT", "120")' not in gconf and "120" not in gconf:
        failures.append("config/gunicorn.conf.py: timeout should default to 120")

    start = _read("scripts/release/render_start_web.sh")
    if "config/gunicorn.conf.py" not in start:
        failures.append("render_start_web.sh: must invoke config/gunicorn.conf.py")

    guard = _read("apps/platform_runtime/middleware_unauthenticated_api_guard.py")
    for needle in (
        "/platform-runtime/workflow-progress/",
        "/assist-dock/",
        "/ws/wal/",
    ):
        if needle not in guard:
            failures.append(f"middleware_unauthenticated_api_guard.py: missing {needle}")

    skeleton = _read("templates/control_plane_skeleton.html")
    if not re.search(
        r"\{% if request\.user\.is_authenticated %\}[\s\S]*?rmc-workflow-progress\.js",
        skeleton,
    ):
        failures.append(
            "control_plane_skeleton.html: rmc-workflow-progress.js must load inside "
            "request.user.is_authenticated block"
        )

    viewport = _read("templates/partials/rmc_viewport_engine.html")
    if "rmc-wal-stream.js" in viewport and "public_host_kind != 'manager'" not in viewport:
        failures.append("rmc_viewport_engine.html: WAL script must skip manager host")

    dashboard = _read("apps/schools/super_views_dashboard_surfaces.py")
    if 'request.method == "POST"' not in dashboard:
        failures.append(
            "super_views_dashboard_surfaces.py: missing POST redirect guard on super_dashboard_v2"
        )
    if "super_dashboard_cache" not in dashboard:
        failures.append(
            "super_views_dashboard_surfaces.py: should use super_dashboard_cache for hot aggregates"
        )

    wfp = _read("apps/platform_runtime/views_workflow_progress.py")
    if "login_required_sse" not in wfp or "login_required_api" not in wfp:
        failures.append("views_workflow_progress.py: must use login_required_api/sse guards")

    assist = _read("apps/assist_dock/views.py")
    if "_SSE_MAX_DURATION_SECONDS = 600" in assist:
        failures.append(
            "assist_dock/views.py: SSE max duration must not hold WSGI threads for 600s"
        )
    if "_sse_max_duration_seconds" not in assist:
        failures.append(
            "assist_dock/views.py: must cap SSE via _sse_max_duration_seconds()"
        )
    if "services.sse_wsgi_limits" not in assist and "sse_wsgi_limits" not in assist:
        failures.append("assist_dock/views.py: must import services.sse_wsgi_limits")

    if not (ROOT / "services" / "sse_wsgi_limits.py").is_file():
        failures.append("services/sse_wsgi_limits.py: missing shared SSE cap helper")

    cmd = _read("apps/schools/super_views_command_center_views.py")
    if "super_dashboard_cache" not in cmd:
        failures.append(
            "super_views_command_center_views.py: must use super_dashboard_cache"
        )

    cache_mod = _read("apps/schools/super_dashboard_cache.py")
    if "get_cached_fleet_registry_metrics" not in cache_mod:
        failures.append("super_dashboard_cache.py: missing fleet metrics cache")

    proc = _read("Procfile")
    yaml = _read("render.yaml")
    if "render_start_web.sh" not in proc:
        failures.append("Procfile: web process must use render_start_web.sh")
    if "render_start_web.sh" not in yaml:
        failures.append("render.yaml: startCommand must use render_start_web.sh")

    if failures:
        print("RENDER_HOTPATH_AUDIT_FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("RENDER_HOTPATH_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
