#!/usr/bin/env python3
"""Tenant portal v3 100x parity gate (batch 1481 + 1484 role-home depth).

Checks portal_base tenant branch for preview header grammar, role-home hero
includes, and legacy dashboard de-dupe gates on parent/teacher/backend landings.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ROLE_HOME_CHECKS = (
    (
        "templates/parent/dashboard.html",
        "parent_show_legacy_dashboard",
        'class="parent-dashboard',
    ),
    (
        "templates/teacher/dashboard.html",
        "teacher_show_legacy_dashboard",
        'class="tdm-bg"',
    ),
    (
        "templates/accounts/backend_dashboard.html",
        "backend_show_legacy_dashboard",
        "backend-dashboard-content",
    ),
)


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def _check_legacy_gate(rel: str, gate_token: str, legacy_token: str) -> str | None:
    body = _text(rel)
    if not body:
        return f"missing {rel}"
    if "hero_greeting.html" not in body:
        return f"{rel}: missing hero_greeting.html include"
    if "tp-dashboard-cockpit" not in body:
        return None
    if legacy_token not in body:
        return None
    gate_idx = body.find(gate_token)
    legacy_idx = body.find(legacy_token)
    if gate_idx < 0 or legacy_idx < 0 or gate_idx > legacy_idx:
        return (
            f"{rel}: legacy block must be gated behind {gate_token} "
            f"(before {legacy_token})"
        )
    return None


def main() -> int:
    findings: list[str] = []

    portal = _text("templates/portal_base.html")
    if not portal:
        findings.append("missing templates/portal_base.html")
        return _fail(findings)

    if "tp-header__row" not in portal:
        findings.append("portal_base.html: missing tp-header__row (tenant v3 preview)")
    if "tenant_primary_nav" not in portal and "tp-primary-nav" not in portal:
        findings.append("portal_base.html: missing tp-primary-nav / tenant_primary_nav include")

    if 'class="navbar navbar-dark topbar' in portal or "navbar-dark topbar" in portal:
        findings.append(
            "portal_base.html: legacy navbar-dark topbar still present — remove for v3"
        )

    css_header = ROOT / "static/css/rmc-tenant-header-100x.css"
    if not css_header.is_file():
        findings.append("missing static/css/rmc-tenant-header-100x.css")

    hero = ROOT / "templates/partials/tenant/hero_greeting.html"
    if not hero.is_file():
        findings.append("missing templates/partials/tenant/hero_greeting.html (tp-hero-row)")
    else:
        hero_text = hero.read_text(encoding="utf-8", errors="replace")
        if "tp_hero_ai_tier_line" not in hero_text:
            findings.append("hero_greeting.html: missing tp_hero_ai_tier_line (PII-safe tier)")

    for rel, gate, legacy in ROLE_HOME_CHECKS:
        err = _check_legacy_gate(rel, gate, legacy)
        if err:
            findings.append(err)

    if findings:
        return _fail(findings)

    print("verify_preview_shell_100x_tenant_parity: PREVIEW_SHELL_TENANT_V3_PARITY_PASS")
    return 0


def _fail(findings: list[str]) -> int:
    print("verify_preview_shell_100x_tenant_parity: FAIL", file=sys.stderr)
    for item in findings:
        print(f"  - {item}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
