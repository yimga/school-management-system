#!/usr/bin/env python3
"""
Phase 2 gate: authenticated shell template conformance.

Focused on high-traffic authenticated surfaces:
- /super/* templates (templates/schools/super_*.html)
- Studio OS templates (templates/studio_os/*.html, templates/studio_os/modes/*.html)

The gate enforces:
1) required base shell hierarchy
2) no direct use of control_plane_skeleton.html outside approved wrappers
3) explicit archetype marker presence on non-fragment /super templates
4) required shell marker contracts remain present in base templates
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "templates"

EXTENDS_RE = re.compile(r'\{\%\s*extends\s+"([^"]+)"\s*\%\}')

CONTROL_PLANE_SKELETON_ALLOWLIST = {
    "templates/control_plane_base.html",
    "templates/auth/admin_login.html",
    "templates/auth/manager_login.html",
    "templates/errors/403_control_plane.html",
    "templates/errors/404_control_plane.html",
    "templates/errors/500_control_plane.html",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _extract_extends(path: Path) -> str | None:
    text = _read(path)
    match = EXTENDS_RE.search(text)
    return match.group(1) if match else None


def main() -> int:
    errors: list[str] = []

    # 1) shell marker contract checks on shared bases
    portal_base = TEMPLATES / "portal_base.html"
    control_plane_base = TEMPLATES / "control_plane_base.html"
    admin_base = TEMPLATES / "admin" / "base.html"

    portal_text = _read(portal_base)
    if 'data-authenticated-surface="{% if request.public_host_kind == \'manager\' %}manager-control-plane{% else %}tenant-portal{% endif %}"' not in portal_text:
        errors.append("portal_base.html missing manager/tenant authenticated-surface contract.")
    if "data-page-archetype" not in portal_text:
        errors.append("portal_base.html missing data-page-archetype contract.")

    cp_text = _read(control_plane_base)
    if 'data-authenticated-surface="manager-control-plane"' not in cp_text:
        errors.append("control_plane_base.html missing manager authenticated-surface marker.")
    if "{% block cp_page_archetype %}" not in cp_text:
        errors.append("control_plane_base.html missing cp_page_archetype block.")

    admin_text = _read(admin_base)
    if 'data-authenticated-surface="{% if is_manager_host %}manager-control-plane{% else %}django-admin{% endif %}"' not in admin_text:
        errors.append("admin/base.html missing manager/django-admin authenticated-surface contract.")

    # 2) /super templates must extend control_plane_base and include archetype marker (non-fragments)
    for path in sorted((TEMPLATES / "schools").glob("super_*.html")):
        rel = path.relative_to(ROOT).as_posix()
        if "_fragment" in path.name:
            continue
        extends = _extract_extends(path)
        if extends != "control_plane_base.html":
            errors.append(f"{rel} must extend control_plane_base.html (found {extends!r}).")
            continue
        text = _read(path)
        if "data-page-archetype" not in text and "cp_page_archetype" not in text:
            errors.append(f"{rel} missing explicit archetype marker (data-page-archetype or cp_page_archetype).")

    # 3) Studio shell hierarchy checks
    studio_shell = TEMPLATES / "studio_os" / "shell.html"
    if _extract_extends(studio_shell) != "portal_base.html":
        errors.append("templates/studio_os/shell.html must extend portal_base.html.")

    mode_dir = TEMPLATES / "studio_os" / "modes"
    for path in sorted(mode_dir.glob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        extends = _extract_extends(path)
        if extends != "studio_os/shell.html":
            errors.append(f"{rel} must extend studio_os/shell.html (found {extends!r}).")

    # 4) only allowlisted templates may directly extend control_plane_skeleton
    for path in TEMPLATES.rglob("*.html"):
        rel = path.relative_to(ROOT).as_posix()
        extends = _extract_extends(path)
        if extends == "control_plane_skeleton.html" and rel not in CONTROL_PLANE_SKELETON_ALLOWLIST:
            errors.append(
                f"{rel} directly extends control_plane_skeleton.html but is not allowlisted."
            )

    if errors:
        print("verify_phase2_authenticated_shell_conformance: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_phase2_authenticated_shell_conformance: PASS "
        "(shell markers + /super hierarchy + Studio hierarchy + skeleton allowlist)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
