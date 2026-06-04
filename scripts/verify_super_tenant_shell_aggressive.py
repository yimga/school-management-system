#!/usr/bin/env python3
"""
Aggressive gate bundle for /super/ (control plane) + tenant portal shells.
Exits 0 with SUPER_TENANT_SHELL_AGGRESSIVE_PASS on full pass.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], label: str) -> list[str]:
    import os

    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=360,
        env=env,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        snippet = "\n".join(out.strip().splitlines()[-15:])
        return [f"{label}: exit {proc.returncode}\n{snippet}"]
    return []


def main() -> int:
    errors: list[str] = []
    py = sys.executable

    checks: list[tuple[str, list[str]]] = [
        ("preview_shell_impl", [py, "scripts/verify_all_preview_shell_html_implementation.py"]),
        ("shell_preview_parity", [py, "scripts/verify_platform_shell_preview_parity.py"]),
        ("manager_portal_chrome", [py, "scripts/verify_manager_portal_chrome_completion.py"]),
        ("interaction_integrity", [py, "scripts/verify_interaction_integrity_completion.py"]),
        ("dead_hrefs", [py, "scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
        ("page_fold", [py, "scripts/verify_page_fold_standards.py"]),
        ("template_safety", [py, "scripts/audit_template_render_safety.py"]),
        ("portal_theme_spine", [py, "scripts/verify_portal_theme_token_spine.py"]),
        ("sidebar_rail", [py, "scripts/verify_sidebar_rail_contract.py"]),
        ("admin_manager_bundle", [py, "scripts/verify_admin_manager_shell_aggressive.py"]),
    ]

    for label, cmd in checks:
        errors.extend(_run(cmd, label))

    cp_base = (ROOT / "templates/control_plane_base.html").read_text(encoding="utf-8")
    cp_sk = (ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    tenant_nav = (ROOT / "templates/partials/tenant_primary_nav.html").read_text(
        encoding="utf-8"
    )

    help_drawer = (ROOT / "templates/partials/help_contextual_drawer.html").read_text(
        encoding="utf-8"
    )

    for needle, path, msg in (
        ("help_contextual_drawer.html", cp_sk, "control_plane_skeleton contextual help"),
        ("_operator_notebook.html", cp_sk, "control_plane_skeleton operator notebook"),
        ("rmc-help-contextual-drawer", help_drawer, "contextual help drawer partial"),
        ("help_contextual_drawer.html", portal, "portal_base contextual help"),
        ("data-rmc-cp-header-200x", cp_base, "control_plane_base header"),
        ("rmc-surface-overlay-guard.js", portal, "portal_base overlay guard"),
        ("tp-primary-nav", tenant_nav, "tenant_primary_nav row"),
        ("rmc-tenant-header-100x.css", portal, "portal tenant header CSS"),
        ("rmc-tenant-canvas-100x.css", portal, "portal tenant canvas CSS"),
    ):
        text = path.read_text(encoding="utf-8") if isinstance(path, Path) else path
        if needle not in text:
            errors.append(f"{msg}: missing {needle}")

    guard = (ROOT / "static/js/rmc-surface-overlay-guard.js").read_text(encoding="utf-8")
    if "portal-body-with-layout" not in guard:
        errors.append("rmc-surface-overlay-guard.js: tenant portal not protected")

    if errors:
        print("SUPER_TENANT_SHELL_AGGRESSIVE_FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("SUPER_TENANT_SHELL_AGGRESSIVE_PASS")
    print(f"  checks: {len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
