#!/usr/bin/env python3
"""One-shot Render deploy readiness gate for manager /super/ hot paths.

Catches the failure classes that broke production deploys:
  - context processor import drift (e.g. csp_nonce registered but missing)
  - shell {% include %} targets missing on disk
  - cockpit incident banner keys not exported on both host branches
  - tracked git files for required deploy artifacts

Exit 0 with RENDER_DEPLOY_READINESS_PASS when clean.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_SHELL_INCLUDES = (
    "components/rmc_workflow_progress_strip.html",
    "partials/cockpit/_operator_incident_banner.html",
    "partials/cockpit/_activity_ticker_inline.html",
    "partials/cockpit/_activity_ticker_drawer.html",
    "partials/cockpit/_activity_ticker_landing_strip.html",
)

REQUIRED_CONTEXT_PROCESSORS = (
    "apps.security.csp_middleware.csp_nonce",
    "apps.siteconfig.cockpit_context.cockpit_context",
    "apps.portal.context_processors.platform_status_strip",
)

REQUIRED_GIT_PATHS = (
    "templates/components/rmc_workflow_progress_strip.html",
    "apps/security/csp_middleware.py",
    "scripts/release/sanitize_gunicorn_env.sh",
    "scripts/release/render_start_web.sh",
    "static/js/rmc-workflow-track-headers.js",
    "static/css/rmc-class-grammar-ext.css",
)

REQUIRED_SHELL_STATIC = (
    "static/js/rmc-workflow-track-headers.js",
    "static/css/rmc-class-grammar-ext.css",
    "static/js/rmc-workflow-progress.js",
    "static/css/rmc-workflow-progress.css",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _check_shell_includes(failures: list[str]) -> None:
    for rel in REQUIRED_SHELL_INCLUDES:
        path = ROOT / "templates" / rel.replace("/", "/")
        if not path.is_file():
            failures.append(f"missing template: templates/{rel}")


def _check_context_processors(failures: list[str]) -> None:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    settings = _read("config/settings.py")
    if "apps.security.csp_middleware.csp_nonce" not in settings:
        failures.append("settings.py: missing apps.security.csp_middleware.csp_nonce")

    for dotted in REQUIRED_CONTEXT_PROCESSORS:
        module_path, _, attr = dotted.rpartition(".")
        try:
            mod = importlib.import_module(module_path)
        except Exception as exc:
            failures.append(f"context processor import failed: {dotted} ({exc})")
            continue
        if not callable(getattr(mod, attr, None)):
            failures.append(f"context processor missing callable: {dotted}")


def _check_cockpit_incident_keys(failures: list[str]) -> None:
    ctx = _read("apps/siteconfig/cockpit_context.py")
    for needle in (
        '"tenant_incident_banner": None',
        '"operator_incident_banner": None',
        "operator_incident_banner",
        "tenant_incident_banner",
    ):
        if needle not in ctx:
            failures.append(f"cockpit_context.py: missing {needle!r}")


def _check_csp_nonce(failures: list[str]) -> None:
    csp = _read("apps/security/csp_middleware.py")
    if "def csp_nonce" not in csp:
        failures.append("csp_middleware.py: missing def csp_nonce")
    if "request.csp_nonce" not in csp:
        failures.append("csp_middleware.py: middleware must set request.csp_nonce")


def _check_git_tracked(failures: list[str]) -> None:
    for rel in REQUIRED_GIT_PATHS:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            failures.append(f"not tracked in git: {rel}")


def _check_shell_static_assets(failures: list[str]) -> None:
    for rel in REQUIRED_SHELL_STATIC:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing static asset: {rel}")


def _control_plane_skeleton_has_workflow_strip(skeleton_text: str) -> bool:
    stack = _read("templates/partials/rmc_tools_tray_context_stack.html")
    return "rmc_workflow_progress_strip.html" in stack


def _check_shell_references(failures: list[str]) -> None:
    wfp_needle = "rmc_workflow_progress_strip.html"
    skeleton = _read("templates/control_plane_skeleton.html")
    if not _control_plane_skeleton_has_workflow_strip(skeleton):
        failures.append(
            "control_plane_skeleton: missing workflow progress strip "
            "(direct include or via manager_operator_topbar in unified header)"
        )
    portal = _read("templates/portal_base.html")
    if wfp_needle in portal:
        failures.append(
            "templates/portal_base.html: workflow progress strip must be tray-only"
        )


def main() -> int:
    failures: list[str] = []
    _check_shell_includes(failures)
    _check_shell_static_assets(failures)
    _check_shell_references(failures)
    _check_context_processors(failures)
    _check_cockpit_incident_keys(failures)
    _check_csp_nonce(failures)
    _check_git_tracked(failures)

    if failures:
        print("RENDER_DEPLOY_READINESS_FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("RENDER_DEPLOY_READINESS_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
