#!/usr/bin/env python3
"""
Platform layout compact — aggregate gate for canvas void + security banner removal.

Exits 0 with PLATFORM_LAYOUT_COMPACT_PASS when all sub-audits pass.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SHELLS = (
    "templates/control_plane_base.html",
    "templates/portal_base.html",
    "templates/admin/base_site.html",
    "templates/base.html",
    "templates/marketing/base_marketing.html",
)
LAYOUT_MARKER = "rmc_security_posture_layout_styles.html"
COMPACT_CSS = "rmc-canvas-chrome-compact.css"
FRAME_MARKER = "rmc_operational_center_frame.html"
HEADER_BLOCK_CP = "block cp_workspace_header"
HEADER_BLOCK_PORTAL = "block rmc_workspace_os_header"
BACK_TO_TOP = "components/back_to_top.html"
SESSION_MODAL = "rmc_security_posture_session_modal.html"
PORTAL_DUP_HEADER_CSS = (
    "body.portal-body-with-layout #main-content .page-wrap:has([data-rmc-operational-center-frame="
)


def _run(script: str, extra: list[str] | None = None) -> tuple[int, str]:
    cmd = [sys.executable, str(ROOT / "scripts" / script)] + (extra or [])
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def audit_shell_coverage() -> list[str]:
    fails: list[str] = []
    for rel in REQUIRED_SHELLS:
        path = ROOT / rel
        if not path.is_file():
            fails.append(f"missing shell: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if LAYOUT_MARKER not in text:
            fails.append(f"shell missing layout styles partial: {rel}")
        partial = ROOT / "templates/partials/rmc_security_posture_layout_styles.html"
        if COMPACT_CSS not in partial.read_text(encoding="utf-8", errors="replace"):
            fails.append("layout styles partial missing compact CSS link")
    return fails


def audit_operational_frame_suppress() -> list[str]:
    missing_cp: list[str] = []
    missing_portal: list[str] = []
    for path in sorted((ROOT / "templates").rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if FRAME_MARKER not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        extends_cp = 'extends "control_plane_base.html"' in text or "extends 'control_plane_base.html'" in text
        extends_portal = (
            'extends "portal_base.html"' in text
            or 'extends "backend_base.html"' in text
            or 'extends "backend_base_tenant.html"' in text
        )
        if extends_cp and HEADER_BLOCK_CP not in text:
            missing_cp.append(rel)
        if extends_portal and not extends_cp and HEADER_BLOCK_PORTAL not in text:
            missing_portal.append(rel)
    fails: list[str] = []
    fails.extend(f"operational frame without cp_workspace_header suppress: {m}" for m in missing_cp)
    fails.extend(
        f"operational frame without rmc_workspace_os_header suppress: {m}" for m in missing_portal
    )
    return fails


def audit_back_to_top_shells() -> list[str]:
    # control_plane_base inherits back_to_top from control_plane_skeleton.html
    shells = [
        "templates/control_plane_skeleton.html",
        "templates/portal_base.html",
        "templates/admin/base_site.html",
        "templates/base.html",
        "templates/marketing/base_marketing.html",
    ]
    fails: list[str] = []
    for rel in shells:
        path = ROOT / rel
        if not path.is_file():
            fails.append(f"missing shell for back_to_top: {rel}")
            continue
        if BACK_TO_TOP not in path.read_text(encoding="utf-8", errors="replace"):
            fails.append(f"shell missing back_to_top: {rel}")
    admin_site = ROOT / "templates/admin/base_site.html"
    if admin_site.is_file() and BACK_TO_TOP not in admin_site.read_text(encoding="utf-8", errors="replace"):
        fails.append("admin/base_site.html missing back_to_top")
    return fails


def audit_portal_dup_header_css() -> list[str]:
    css = ROOT / "static/css/rmc-canvas-chrome-compact.css"
    if not css.is_file():
        return ["missing rmc-canvas-chrome-compact.css"]
    text = css.read_text(encoding="utf-8", errors="replace")
    if PORTAL_DUP_HEADER_CSS not in text:
        return ["compact CSS missing portal operational-frame duplicate header rule"]
    return []


def main() -> int:
    failures: list[str] = []
    failures.extend(audit_shell_coverage())
    failures.extend(audit_operational_frame_suppress())
    failures.extend(audit_back_to_top_shells())
    failures.extend(audit_portal_dup_header_css())

    sub_gates = [
        ("audit_canvas_chrome_void.py", []),
        ("audit_security_posture_banner_layout.py", []),
        ("audit_surface_spacing_contract.py", ["--strict", "--write"]),
        ("verify_page_fold_standards.py", []),
        ("verify_interaction_integrity_completion.py", []),
        ("scan_operator_shell_dead_hrefs.py", ["--strict"]),
        ("audit_preview_html_platform_grass.py", ["--write"]),
        ("verify_all_preview_shell_html_implementation.py", []),
        ("verify_platform_shell_preview_parity.py", []),
    ]
    for script, extra in sub_gates:
        code, out = _run(script, extra)
        if code != 0:
            failures.append(f"{script} failed (exit {code})")
            if out:
                failures.append(out.splitlines()[-1] if out else "")

    if failures:
        print("PLATFORM_LAYOUT_COMPACT_FAIL")
        for item in failures:
            if item:
                print(f"  - {item}")
        return 1

    print("PLATFORM_LAYOUT_COMPACT_PASS")
    print("  canvas_chrome_void: PASS")
    print("  security_posture_nav_modal: PASS")
    print("  surface_spacing_contract (strict): PASS")
    print("  page_fold_standards: PASS")
    print("  interaction_integrity: PASS")
    print("  operator_dead_hrefs (strict): PASS")
    print("  preview_html_platform_grass: PASS (3 canonical HTML north stars)")
    print("  all_preview_shell_html_implementation: PASS")
    print("  platform_shell_preview_parity: PASS")
    print(f"  operational_frame_templates: all suppress duplicate workspace header")
    print(f"  authenticated_shells: {len(REQUIRED_SHELLS)}/5 load compact CSS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
