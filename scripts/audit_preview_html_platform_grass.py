#!/usr/bin/env python3
"""
Aggressive preview-HTML ↔ production grass audit.

North-star references (canonical — do not fork):
  - docs/generated/preview_app_shell_manager_v8_200x.html   (/super/)
  - docs/generated/preview_app_shell_admin_v1_200x.html     (/admin/ manager)
  - docs/generated/preview_app_shell_tenant_portal_v3_100x.html (tenant portal)

Exits 0 with PREVIEW_HTML_PLATFORM_GRASS_PASS when preview DOM order, production
wiring, layout-compact contract, and preview implementation gates all pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/generated/preview_html_platform_grass_audit.json"

CANONICAL_PREVIEWS: dict[str, str] = {
    "manager-v8-200x": "docs/generated/preview_app_shell_manager_v8_200x.html",
    "admin-v1-200x": "docs/generated/preview_app_shell_admin_v1_200x.html",
    "tenant-portal-v3-100x": "docs/generated/preview_app_shell_tenant_portal_v3_100x.html",
}

# Production must implement preview markers (direct or via {% include %} partials).
PRODUCTION_WIRING: dict[str, list[tuple[str, tuple[str, ...]]]] = {
    "manager-v8-200x": [
        ("docs/generated/preview_app_shell_manager_v8_200x.html", ("cp-activity-ticker", "cp-primary-nav", "rmc-app-shell__copilot")),
        ("templates/control_plane_base.html", ("control_plane_unified_header.html", "shell_chrome_security_posture", "rmc_security_posture_layout_styles")),
        ("templates/partials/control_plane_unified_header.html", ("cp_shell_header_ticker", "cp-header__row--live", "cp-header__row--inline-chrome")),
        ("templates/partials/control_plane_primary_nav.html", ("cp-primary-nav", "rmc_security_posture_nav_button")),
        ("templates/partials/cockpit/_activity_ticker.html", ("cp-live-strip", "cp-activity-ticker")),
        ("templates/partials/rmc_security_posture_layout_styles.html", ("rmc-canvas-chrome-compact.css",)),
        ("templates/control_plane_skeleton.html", ("back_to_top", "help_contextual_drawer")),
    ],
    "admin-v1-200x": [
        ("docs/generated/preview_app_shell_admin_v1_200x.html", ("cp-nav-row", "cp-live-strip", "cp-hero", "cp-catalog-card")),
        ("templates/admin/base.html", ("control_plane_unified_header.html", "shell_chrome_security_posture")),
        ("templates/control_plane_skeleton.html", ("back_to_top",)),
        ("templates/admin/base_site.html", ("rmc_security_posture_layout_styles", "rmc-admin-v1-200x.css", "back_to_top")),
        ("templates/partials/control_plane_primary_nav.html", ("rmc_security_posture_nav_button",)),
    ],
    "tenant-portal-v3-100x": [
        ("docs/generated/preview_app_shell_tenant_portal_v3_100x.html", ("tp-header", "tp-primary-nav", "tp-sidebar-inner")),
        ("templates/portal_base.html", ("tenant_primary_nav.html", "shell_chrome_security_posture", "rmc_security_posture_layout_styles", "back_to_top")),
        ("templates/partials/tenant_primary_nav.html", ("tp-primary-nav",)),
    ],
}

# DOM order inside preview HTML <body> (first token must precede second).
PREVIEW_BODY_ORDER: dict[str, tuple[str, str]] = {
    "manager-v8-200x": ("cp-activity-ticker", "cp-primary-nav"),
    "admin-v1-200x": ("cp-nav-row", "cp-live-strip"),
    "tenant-portal-v3-100x": ("tp-header__row", "tp-primary-nav"),
}

# Production template order (substring positions).
PRODUCTION_ORDER: dict[str, tuple[str, str, str]] = {
    "manager-v8-200x": (
        "templates/partials/control_plane_unified_header.html",
        "cp-header__row--live",
        "cp-header__row--inline-chrome",
    ),
    "admin-v1-200x": (
        "templates/partials/control_plane_unified_header.html",
        "cp-header__row--live",
        "cp-header__row--inline-chrome",
    ),
}


def _read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _body_pos(html: str, token: str) -> int:
    idx = html.lower().find("<body")
    body = html[idx:] if idx >= 0 else html
    return body.find(token)


def audit_preview_files() -> list[str]:
    fails: list[str] = []
    for slug, rel in CANONICAL_PREVIEWS.items():
        path = ROOT / rel
        if not path.is_file():
            fails.append(f"missing canonical preview HTML: {rel} ({slug})")
            continue
        if path.stat().st_size < 2048:
            fails.append(f"preview HTML too small (corrupt?): {rel}")
    return fails


def audit_preview_body_order() -> list[str]:
    fails: list[str] = []
    for slug, (first, second) in PREVIEW_BODY_ORDER.items():
        rel = CANONICAL_PREVIEWS[slug]
        text = _read(rel)
        p1, p2 = _body_pos(text, first), _body_pos(text, second)
        if p1 < 0 or p2 < 0 or p1 > p2:
            fails.append(
                f"preview {rel}: body order requires {first} before {second} "
                f"(per PREVIEW_SHELL_100X_PARITY_PLAN)"
            )
    return fails


def audit_production_wiring() -> list[str]:
    fails: list[str] = []
    for slug, checks in PRODUCTION_WIRING.items():
        for rel, needles in checks:
            text = _read(rel)
            if not text and not rel.startswith("docs/"):
                fails.append(f"[{slug}] missing production file: {rel}")
                continue
            for needle in needles:
                if needle not in text:
                    fails.append(f"[{slug}] {rel}: missing preview contract marker `{needle}`")
    return fails


def audit_production_order() -> list[str]:
    fails: list[str] = []
    for slug, (rel, first, second) in PRODUCTION_ORDER.items():
        text = _read(rel)
        p1, p2 = text.find(first), text.find(second)
        if p1 < 0 or p2 < 0 or p1 > p2:
            fails.append(
                f"[{slug}] {rel}: production order requires `{first}` before `{second}` "
                f"(matches {CANONICAL_PREVIEWS[slug]})"
            )
    return fails


def audit_operational_frame_portal_suppress() -> list[str]:
    fails: list[str] = []
    for path in sorted((ROOT / "templates").rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "rmc_operational_center_frame.html" not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        extends_cp = "control_plane_base.html" in text
        extends_portal = "portal_base.html" in text or "backend_base.html" in text
        if extends_cp and "block cp_workspace_header" not in text:
            fails.append(f"{rel}: operational frame missing cp_workspace_header suppress")
        if extends_portal and not extends_cp and "block rmc_workspace_os_header" not in text:
            fails.append(f"{rel}: operational frame missing rmc_workspace_os_header suppress")
    return fails


def _run_gate(script: str, extra: list[str] | None = None) -> tuple[bool, str]:
    cmd = [sys.executable, str(ROOT / "scripts" / script)] + (extra or [])
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    line = out.splitlines()[-1] if out else ""
    return proc.returncode == 0, line


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    checks: dict[str, list[str]] = {
        "preview_files": audit_preview_files(),
        "preview_body_order": audit_preview_body_order(),
        "production_wiring": audit_production_wiring(),
        "production_order": audit_production_order(),
        "operational_frame_suppress": audit_operational_frame_portal_suppress(),
    }
    gate_scripts = [
        "audit_canvas_chrome_void.py",
        "audit_security_posture_banner_layout.py",
        "verify_all_preview_shell_html_implementation.py",
        "verify_platform_shell_preview_parity.py",
    ]
    gate_results: dict[str, str] = {}
    for script in gate_scripts:
        ok, line = _run_gate(script)
        gate_results[script] = line or ("PASS" if ok else "FAIL")
        if not ok:
            checks.setdefault("sub_gates", []).append(f"{script} failed: {line}")

    failures: list[str] = []
    for items in checks.values():
        failures.extend(items)

    report = {
        "canonical_previews": CANONICAL_PREVIEWS,
        "finding_count": len(failures),
        "findings": [{"message": m} for m in failures],
        "checks": {k: len(v) for k, v in checks.items()},
        "sub_gates": gate_results,
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "remediation_status": "PASS" if not failures else "FAIL",
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("PREVIEW_HTML_PLATFORM_GRASS_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("PREVIEW_HTML_PLATFORM_GRASS_PASS")
    for slug, rel in CANONICAL_PREVIEWS.items():
        print(f"  preview: {rel}")
    for script, line in gate_results.items():
        print(f"  {script}: {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
