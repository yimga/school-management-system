#!/usr/bin/env python3
"""
Platform audit: quarterly security posture inline banner + canvas void fix.

Exits 0 with SECURITY_POSTURE_BANNER_LAYOUT_PASS when:
- Canonical shell partial is wired on control_plane_base, portal_base, manager admin
- Layout contract CSS is loaded on all three authenticated shell heads
- Every /super/ page template inherits control_plane_base (or skeleton-only exempt list)
- No duplicate direct includes of _security_posture_banner.html
- Layout contract CSS ships min-height:0 on banner + canvas flex-shrink rules
- Corner toast is suppressed when inline banner is active (Python contract)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUT = ROOT / "docs/generated/security_posture_banner_layout_audit.json"
STATIC_CSS = ROOT / "static/css/rmc-security-posture-banner-layout.css"
STATIC_JS = ROOT / "static/js/rmc-security-posture-banner.js"

SHELL_INCLUDE = '{% include "partials/shell_chrome_security_posture_banner.html" %}'
LAYOUT_STYLE_MARKER = "rmc_security_posture_layout_styles.html"
SHELL_PARTIAL = TEMPLATES / "partials" / "shell_chrome_security_posture_banner.html"
BANNER_PARTIAL = TEMPLATES / "accounts" / "partials" / "_security_posture_banner.html"

REQUIRED_SHELLS = (
    TEMPLATES / "control_plane_base.html",
    TEMPLATES / "portal_base.html",
    TEMPLATES / "admin" / "base.html",
)

LAYOUT_STYLE_SHELLS = (
    TEMPLATES / "control_plane_base.html",
    TEMPLATES / "portal_base.html",
    TEMPLATES / "admin" / "base_site.html",
)

SKELETON_ONLY_EXEMPT = frozenset(
    {
        "templates/auth/admin_login.html",
        "templates/auth/manager_login.html",
        "templates/errors/403_control_plane.html",
        "templates/errors/404_control_plane.html",
        "templates/errors/500_control_plane.html",
        "templates/errors/503_control_plane.html",
    }
)

EXTENDS_CP_BASE = re.compile(
    r"""extends\s+['"]control_plane_base\.html['"]""",
    re.IGNORECASE,
)
EXTENDS_CP_SKELETON = re.compile(
    r"""extends\s+['"]control_plane_skeleton\.html['"]""",
    re.IGNORECASE,
)
DIRECT_BANNER_INCLUDE = re.compile(
    r"""include\s+['"]accounts/partials/_security_posture_banner\.html['"]""",
    re.IGNORECASE,
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def audit_super_template_coverage() -> list[str]:
    failures: list[str] = []
    super_candidates: list[Path] = []
    covered = 0
    for path in TEMPLATES.rglob("*.html"):
        rel = _rel(path)
        if rel.startswith("templates/schools/super_") or rel.startswith("templates/super/"):
            super_candidates.append(path)
        elif "/super/" in rel.replace("\\", "/"):
            super_candidates.append(path)

    for path in sorted(super_candidates):
        rel = _rel(path)
        name = path.name.lower()
        if "fragment" in name or name.startswith("_") or "/includes/" in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "{% extends" not in text:
            continue
        if EXTENDS_CP_BASE.search(text):
            covered += 1
            continue
        if EXTENDS_CP_SKELETON.search(text) and rel in SKELETON_ONLY_EXEMPT:
            covered += 1
            continue
        failures.append(f"super template not on control_plane_base chain: {rel}")

    if covered < 1:
        failures.append("no super templates found on control_plane_base chain")
    return failures


def audit_shell_wiring() -> list[str]:
    failures: list[str] = []
    if not SHELL_PARTIAL.is_file():
        failures.append(f"missing shell partial: {_rel(SHELL_PARTIAL)}")
    if not BANNER_PARTIAL.is_file():
        failures.append(f"missing banner partial: {_rel(BANNER_PARTIAL)}")
    if not STATIC_JS.is_file():
        failures.append(f"missing banner JS: {_rel(STATIC_JS)}")
    for shell in REQUIRED_SHELLS:
        if not shell.is_file():
            failures.append(f"missing shell template: {_rel(shell)}")
            continue
        if SHELL_INCLUDE not in shell.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"shell missing security posture include: {_rel(shell)}")
    return failures


def audit_layout_style_shells() -> list[str]:
    failures: list[str] = []
    partial = TEMPLATES / "partials" / "rmc_security_posture_layout_styles.html"
    if not partial.is_file():
        failures.append(f"missing layout style partial: {_rel(partial)}")
        return failures
    for shell in LAYOUT_STYLE_SHELLS:
        if not shell.is_file():
            failures.append(f"missing layout shell head: {_rel(shell)}")
            continue
        if LAYOUT_STYLE_MARKER not in shell.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"shell missing layout style include: {_rel(shell)}")
    manager_backend = TEMPLATES / "backend_base_manager.html"
    if manager_backend.is_file():
        text = manager_backend.read_text(encoding="utf-8", errors="replace")
        if not EXTENDS_CP_BASE.search(text):
            failures.append("backend_base_manager.html must extend control_plane_base")
    return failures


def audit_no_duplicate_includes() -> list[str]:
    failures: list[str] = []
    for path in TEMPLATES.rglob("*.html"):
        if path == SHELL_PARTIAL:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if DIRECT_BANNER_INCLUDE.search(text):
            failures.append(
                f"direct _security_posture_banner include (use shell partial): {_rel(path)}"
            )
    return failures


def audit_layout_css() -> list[str]:
    failures: list[str] = []
    if not STATIC_CSS.is_file():
        failures.append(f"missing layout CSS: {_rel(STATIC_CSS)}")
        return failures
    css = STATIC_CSS.read_text(encoding="utf-8", errors="replace")
    required_fragments = (
        '[data-rmc-security-posture-banner="1"]',
        "flex: 0 1 auto",
        'data-rmc-cp-scroll="canvas"',
    )
    for frag in required_fragments:
        if frag not in css:
            failures.append(f"layout CSS missing fragment: {frag}")
    if "min-height: 0 !important" not in css:
        failures.append("layout CSS missing banner min-height guard")
    return failures


def audit_corner_suppression_contract() -> list[str]:
    failures: list[str] = []
    mod = ROOT / "apps" / "accounts" / "security_posture_notifications.py"
    text = mod.read_text(encoding="utf-8", errors="replace")
    if "inline_security_posture_banner_active" not in text:
        failures.append("missing inline_security_posture_banner_active()")
    if "if inline_security_posture_banner_active(request):" not in text:
        failures.append("corner_notifications_for_request must gate on inline banner")
    ctx = ROOT / "apps" / "accounts" / "context_processors_security.py"
    ctx_text = ctx.read_text(encoding="utf-8", errors="replace")
    for key in (
        "security_posture_corner_snoozed",
        "security_posture_inline_banner",
    ):
        if key not in ctx_text:
            failures.append(f"context_processors_security missing {key}")
    return failures


def audit_banner_collapsible_markup() -> list[str]:
    failures: list[str] = []
    text = BANNER_PARTIAL.read_text(encoding="utf-8", errors="replace")
    for token in (
        "<details",
        "rmc-collapsable",
        "rmc-collapsable__head",
        "data-rmc-security-posture-banner",
        "data-rmc-security-posture-snooze",
    ):
        if token not in text:
            failures.append(f"banner partial missing collapsible token: {token}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks = {
        "shell_wiring": audit_shell_wiring(),
        "layout_style_shells": audit_layout_style_shells(),
        "super_template_coverage": audit_super_template_coverage(),
        "no_duplicate_includes": audit_no_duplicate_includes(),
        "layout_css": audit_layout_css(),
        "corner_suppression": audit_corner_suppression_contract(),
        "collapsible_markup": audit_banner_collapsible_markup(),
    }
    failures: list[str] = []
    for items in checks.values():
        failures.extend(items)

    report = {
        "finding_count": len(failures),
        "findings": [{"message": f} for f in failures],
        "checks": {k: len(v) for k, v in checks.items()},
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "remediation_status": "PASS" if not failures else "FAIL",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("SECURITY_POSTURE_BANNER_LAYOUT_FAIL")
        for item in failures:
            print(f"  - {item}")
    else:
        print("SECURITY_POSTURE_BANNER_LAYOUT_PASS")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
