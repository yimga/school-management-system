#!/usr/bin/env python3
"""
Platform audit: security posture nav + per-session modal (all authenticated shells).

Exits 0 with SECURITY_POSTURE_BANNER_LAYOUT_PASS when:
- Session modal shell partial wired on control_plane_base, portal_base, manager admin
- Layout nav CSS loaded on shell heads
- Primary nav includes security posture control
- No duplicate direct includes of legacy _security_posture_banner.html
- Context + notifications module expose zone + session modal contract
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
STATIC_NAV_CSS = ROOT / "static/css/rmc-security-posture-nav.css"
STATIC_MODAL_JS = ROOT / "static/js/rmc-security-posture-session-modal.js"

SHELL_INCLUDE = '{% include "partials/shell_chrome_security_posture_banner.html" %}'
LAYOUT_STYLE_MARKER = "rmc_security_posture_layout_styles.html"
NAV_BUTTON_MARKER = '{% include "partials/rmc_security_posture_nav_button.html" %}'
SHELL_PARTIAL = TEMPLATES / "partials" / "shell_chrome_security_posture_banner.html"
MODAL_PARTIAL = TEMPLATES / "partials" / "rmc_security_posture_session_modal.html"
LEGACY_BANNER = TEMPLATES / "accounts" / "partials" / "_security_posture_banner.html"

REQUIRED_SHELLS = (
    TEMPLATES / "control_plane_base.html",
    TEMPLATES / "portal_base.html",
    TEMPLATES / "admin" / "base.html",
)

LAYOUT_STYLE_SHELLS = (
    TEMPLATES / "control_plane_base.html",
    TEMPLATES / "portal_base.html",
    TEMPLATES / "admin" / "base_site.html",
    TEMPLATES / "marketing" / "base_marketing.html",
)

PRIMARY_NAV = TEMPLATES / "partials" / "control_plane_primary_nav.html"

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
EXTENDS_ANY = re.compile(
    r"""extends\s+['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
DIRECT_BANNER_INCLUDE = re.compile(
    r"""include\s+['"]accounts/partials/_security_posture_banner\.html['"]""",
    re.IGNORECASE,
)


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _on_control_plane_base_chain(text: str) -> bool:
    if EXTENDS_CP_BASE.search(text):
        return True
    match = EXTENDS_ANY.search(text)
    if not match:
        return False
    parent_rel = match.group(1).replace("\\", "/")
    parent_path = TEMPLATES / parent_rel
    if not parent_path.is_file():
        parent_path = ROOT / "templates" / parent_rel
    if not parent_path.is_file():
        return False
    parent_text = parent_path.read_text(encoding="utf-8", errors="replace")
    return bool(EXTENDS_CP_BASE.search(parent_text))


def audit_super_template_coverage() -> list[str]:
    failures: list[str] = []
    super_candidates: list[Path] = []
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
        if _on_control_plane_base_chain(text):
            continue
        if EXTENDS_CP_SKELETON.search(text) and rel in SKELETON_ONLY_EXEMPT:
            continue
        failures.append(f"super template not on control_plane_base chain: {rel}")

    if not super_candidates:
        failures.append("no super templates found")
    return failures


def audit_shell_wiring() -> list[str]:
    failures: list[str] = []
    if not SHELL_PARTIAL.is_file():
        failures.append(f"missing shell partial: {_rel(SHELL_PARTIAL)}")
    if not MODAL_PARTIAL.is_file():
        failures.append(f"missing session modal partial: {_rel(MODAL_PARTIAL)}")
    if not STATIC_MODAL_JS.is_file():
        failures.append(f"missing session modal JS: {_rel(STATIC_MODAL_JS)}")
    shell_text = SHELL_PARTIAL.read_text(encoding="utf-8", errors="replace") if SHELL_PARTIAL.is_file() else ""
    if "rmc_security_posture_session_modal" not in shell_text:
        failures.append("shell partial must include session modal, not legacy inline banner")
    if "_security_posture_banner.html" in shell_text:
        failures.append("shell partial must not include legacy inline banner")
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
    nav_css = partial.read_text(encoding="utf-8", errors="replace")
    if "rmc-security-posture-nav.css" not in nav_css:
        failures.append("layout style partial must link rmc-security-posture-nav.css")
    for shell in LAYOUT_STYLE_SHELLS:
        if not shell.is_file():
            failures.append(f"missing layout shell head: {_rel(shell)}")
            continue
        text = shell.read_text(encoding="utf-8", errors="replace")
        if LAYOUT_STYLE_MARKER not in text and shell.name != "base_marketing.html":
            failures.append(f"shell missing layout style include: {_rel(shell)}")
        if shell.name == "base_marketing.html" and "rmc_security_posture_layout_styles" not in text:
            failures.append("marketing shell missing conditional layout styles")
    return failures


def audit_nav_button_wiring() -> list[str]:
    failures: list[str] = []
    if not PRIMARY_NAV.is_file():
        failures.append(f"missing primary nav: {_rel(PRIMARY_NAV)}")
        return failures
    if NAV_BUTTON_MARKER not in PRIMARY_NAV.read_text(encoding="utf-8", errors="replace"):
        failures.append("control_plane_primary_nav missing security nav button")
    portal = TEMPLATES / "portal_base.html"
    if NAV_BUTTON_MARKER not in portal.read_text(encoding="utf-8", errors="replace"):
        failures.append("portal_base missing security nav button in header actions")
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


def audit_nav_css() -> list[str]:
    failures: list[str] = []
    if not STATIC_NAV_CSS.is_file():
        failures.append(f"missing nav CSS: {_rel(STATIC_NAV_CSS)}")
        return failures
    css = STATIC_NAV_CSS.read_text(encoding="utf-8", errors="replace")
    for frag in (
        ".rmc-security-posture-nav--critical",
        ".rmc-security-posture-nav--warning",
        ".rmc-security-posture-nav--ok",
        "prefers-reduced-motion",
        "rmc-security-pulse-fast",
    ):
        if frag not in css:
            failures.append(f"nav CSS missing fragment: {frag}")
    return failures


def audit_session_modal_contract() -> list[str]:
    failures: list[str] = []
    mod = ROOT / "apps" / "accounts" / "security_posture_notifications.py"
    text = mod.read_text(encoding="utf-8", errors="replace")
    for token in (
        "SESSION_MODAL_ACK_KEY",
        "security_posture_zone",
        "should_show_session_modal",
        "acknowledge_session_modal",
    ):
        if token not in text:
            failures.append(f"security_posture_notifications missing {token}")
    ctx = ROOT / "apps" / "accounts" / "context_processors_security.py"
    ctx_text = ctx.read_text(encoding="utf-8", errors="replace")
    for key in (
        "security_posture_zone",
        "security_posture_session_modal_show",
        "security_posture_inline_banner",
    ):
        if key not in ctx_text:
            failures.append(f"context_processors_security missing {key}")
    if "security_posture_inline_banner\": False" not in ctx_text:
        failures.append("inline banner must be disabled in context processor")
    modal = MODAL_PARTIAL.read_text(encoding="utf-8", errors="replace")
    for token in (
        "rmcSecurityPostureSessionModal",
        "data-rmc-security-posture-modal-close",
        "security_posture_session_modal_ack",
    ):
        if token not in modal:
            failures.append(f"session modal partial missing {token}")
    legacy = LEGACY_BANNER.read_text(encoding="utf-8", errors="replace")
    if "rmc-security-posture-banner" in legacy or "Account below minimum" in legacy:
        failures.append("legacy _security_posture_banner must be empty (use nav+modal)")
    compact = ROOT / "static/css/rmc-canvas-chrome-compact.css"
    if not compact.is_file():
        failures.append("missing rmc-canvas-chrome-compact.css")
    else:
        layout_partial = TEMPLATES / "partials" / "rmc_security_posture_layout_styles.html"
        if "rmc-canvas-chrome-compact.css" not in layout_partial.read_text(
            encoding="utf-8", errors="replace"
        ):
            failures.append("layout styles must link rmc-canvas-chrome-compact.css")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    checks = {
        "shell_wiring": audit_shell_wiring(),
        "layout_style_shells": audit_layout_style_shells(),
        "nav_button_wiring": audit_nav_button_wiring(),
        "super_template_coverage": audit_super_template_coverage(),
        "no_duplicate_includes": audit_no_duplicate_includes(),
        "nav_css": audit_nav_css(),
        "session_modal_contract": audit_session_modal_contract(),
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
