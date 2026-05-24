#!/usr/bin/env python3
"""
Aggressive gate bundle for manager /admin/ + control-plane shell parity (v3.62.17+).
Exits 0 with ADMIN_MANAGER_SHELL_AGGRESSIVE_PASS on full pass.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], label: str) -> list[str]:
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        snippet = "\n".join(out.strip().splitlines()[-12:])
        return [f"{label}: exit {proc.returncode}\n{snippet}"]
    return []


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--css-only",
        action="store_true",
        help="Fast path: shell parity + layout only (preview shell 100x phase 2)",
    )
    args = parser.parse_args()

    errors: list[str] = []
    py = sys.executable

    checks: list[tuple[str, list[str]]] = [
        ("preview_shell_impl", [py, "scripts/verify_all_preview_shell_html_implementation.py"]),
        ("shell_preview_parity", [py, "scripts/verify_platform_shell_preview_parity.py"]),
        ("manager_admin_layout", [py, "scripts/verify_manager_admin_cp_layout.py"]),
    ]
    if not args.css_only:
        checks.extend(
            [
                ("interaction_integrity", [py, "scripts/verify_interaction_integrity_completion.py"]),
                ("dead_hrefs", [py, "scripts/scan_operator_shell_dead_hrefs.py", "--strict"]),
                ("page_fold", [py, "scripts/verify_page_fold_standards.py"]),
                ("template_safety", [py, "scripts/audit_template_render_safety.py"]),
                ("admin_gear_up", [py, "scripts/verify_admin_platform_gear_up_bundle.py"]),
                ("admin_changelist", [py, "scripts/verify_admin_changelist_render_contract.py"]),
                ("admin_steering", [py, "scripts/verify_admin_steering_strip_contract.py"]),
                ("manager_chrome", [py, "scripts/verify_manager_portal_chrome_completion.py"]),
            ]
        )

    for label, cmd in checks:
        errors.extend(_run(cmd, label))

    index = (ROOT / "templates/admin/index_superadmin.html").read_text(encoding="utf-8")
    for needle in (
        "rmc-page-fold-nav",
        "data-rmc-section-anchor",
        'class="rmc-admin-catalog-section" id=',
        "data-rmc-admin-catalog-section",
        "admin_v1_index_surface_previews",
    ):
        if needle not in index:
            errors.append(f"index_superadmin.html: missing {needle}")

    help_drawer = (ROOT / "templates/partials/help_contextual_drawer.html").read_text(encoding="utf-8")
    if "rmc-help-contextual-drawer" not in help_drawer or "Need help on this page?" not in help_drawer:
        errors.append("help_contextual_drawer.html: contextual help chip missing")

    skeleton = (ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if "help_contextual_drawer.html" not in skeleton or "rmc-footer-notebook-anchor" not in skeleton:
        errors.append("control_plane_skeleton.html: contextual help drawer or footer notebook anchor missing")

    guard = (ROOT / "static/js/rmc-surface-overlay-guard.js").read_text(encoding="utf-8")
    if "MutationObserver" not in guard or 'getElementById("modal-overlay")' not in guard:
        errors.append("rmc-surface-overlay-guard.js: incomplete overlay guard")

    if errors:
        print("ADMIN_MANAGER_SHELL_AGGRESSIVE_FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("ADMIN_MANAGER_SHELL_AGGRESSIVE_PASS")
    print(f"  checks: {len(checks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
