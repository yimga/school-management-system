#!/usr/bin/env python3
"""Nav engine coverage — spine rows reverse; tenant projector wired; no HTML role tree."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _static_checks() -> list[str]:
    failures: list[str] = []
    portal = (ROOT / "apps/siteconfig/portal_sidebar_items.py").read_text(
        encoding="utf-8"
    )
    if "TENANT_STAFF_SPINE" not in portal:
        failures.append("portal_sidebar_items.py does not import TENANT_STAFF_SPINE")
    if "STAFF_PRIMARY_ROLES" not in portal:
        failures.append("portal_sidebar_items.py does not use STAFF_PRIMARY_ROLES")
    engine = (ROOT / "apps/platform_runtime/nav_engine.py").read_text(encoding="utf-8")
    if '"HOD"' not in engine and "'HOD'" not in engine:
        failures.append("nav_engine.py missing HOD in staff primary roles")
    cp = (ROOT / "apps/schools/control_plane_nav.py").read_text(encoding="utf-8")
    if "operator_items_for_group" not in cp:
        failures.append("control_plane_nav.py does not merge operator_items_for_group")
    cmd = (ROOT / "apps/siteconfig/command_bar_registry.py").read_text(encoding="utf-8")
    if "command_bar_extra_defs" not in cmd:
        failures.append("command_bar_registry.py does not federate nav_engine extras")
    groups = {
        line.split('"')[1]
        for line in engine.splitlines()
        if line.strip().startswith('group="')
    }
    for label in groups:
        needle = f'"{label}"'
        if needle not in cp:
            failures.append(f"operator group {label!r} missing from control_plane_nav.py")
    sidebar = (ROOT / "templates/partials/portal_sidebar.html").read_text(
        encoding="utf-8"
    )
    if "portal:teacher_feed" in sidebar:
        failures.append("portal_sidebar.html still has hardcoded teacher fallback tree")
    if "nav_role == 'TEACHER'" in sidebar:
        failures.append("portal_sidebar.html still branches a teacher fallback tree")
    if "not PORTAL_SIDEBAR_ITEMS and request.user.is_authenticated and EFFECTIVE_PORTAL_ROLE == 'TEACHER'" in sidebar:
        failures.append("portal_sidebar.html still has teacher-only HTML fallback nav")
    return failures


def _django_checks() -> list[str]:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.urls import NoReverseMatch, reverse, set_urlconf

    from apps.platform_runtime.nav_engine import OPERATOR_SPINE, TENANT_STAFF_SPINE

    failures: list[str] = []
    set_urlconf("config.tenant_urls")
    for spec in TENANT_STAFF_SPINE:
        try:
            url = reverse(spec.url_name)
        except NoReverseMatch:
            failures.append(f"tenant reverse failed: {spec.id} {spec.url_name}")
        else:
            if not url:
                failures.append(f"tenant empty url: {spec.id}")
    set_urlconf("config.manager_urls")
    for spec in OPERATOR_SPINE:
        try:
            url = reverse(spec.url_name, urlconf="config.manager_urls")
        except NoReverseMatch:
            failures.append(f"operator reverse failed: {spec.id} {spec.url_name}")
        else:
            if not url:
                failures.append(f"operator empty url: {spec.id}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()
    failures = _static_checks()
    if not args.static_only:
        failures.extend(_django_checks())
    if failures:
        print("verify_nav_engine_coverage: FAIL", file=sys.stderr)
        for row in failures:
            print(f"  - {row}", file=sys.stderr)
        return 1
    print("verify_nav_engine_coverage: NAV_ENGINE_COVERAGE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
