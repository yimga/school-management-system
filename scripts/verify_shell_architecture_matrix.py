#!/usr/bin/env python3
"""
Shell triad matrix verifier.

Enforces the minimum architecture contracts for the four shell surfaces:
- marketing
- control-plane (/super + manager host surfaces)
- admin backoffice
- tenant base

Also checks release-evidence docs still reference this script and Phase H (BR-13 / P4),
without replacing per-hostname manual passes on staging/production.

Batch 42 §11.4: Studio OS root shell extends ``portal_base`` and must not inline
control-plane or marketing shell CSS (same contract as tenant portal spine).
"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def _check_contains(errors: list[str], rel_path: str, must_include: list[str]) -> None:
    text = _read(rel_path)
    for token in must_include:
        if token not in text:
            errors.append(f"{rel_path} missing required token: {token!r}")


def _check_not_contains(errors: list[str], rel_path: str, must_not_include: list[str]) -> None:
    text = _read(rel_path)
    for token in must_not_include:
        if token in text:
            errors.append(f"{rel_path} contains forbidden token: {token!r}")


def _check_file_exists(errors: list[str], rel_path: str) -> None:
    if not (ROOT / rel_path).is_file():
        errors.append(f"missing required file: {rel_path}")


def main() -> int:
    errors: list[str] = []

    # Canonical architecture doc + core nav tests should stay present.
    _check_file_exists(errors, "docs/SHELL_ARCHITECTURE_MATRIX.md")
    _check_contains(
        errors,
        "docs/SHELL_ARCHITECTURE_MATRIX.md",
        [
            "verify_shell_architecture_matrix.py",
            "Duplicate-bundle sweep",
            "Repository audit log",
            "Staging / production URL matrix",
            "Operator sign-off log",
        ],
    )
    _check_file_exists(errors, "docs/PREMIUM_UX_MANUAL_PASS_BR13.md")
    _check_contains(
        errors,
        "docs/PREMIUM_UX_MANUAL_PASS_BR13.md",
        [
            "verify_shell_architecture_matrix.py",
            "Phase H",
        ],
    )
    _check_file_exists(errors, "apps/schools/tests/test_primary_control_plane_nav.py")
    _check_file_exists(errors, "apps/schools/tests/test_control_plane_nav_roles.py")

    # Marketing shell: marketing marker + marketing css; no control-plane shell css.
    _check_contains(
        errors,
        "templates/marketing/base_marketing.html",
        [
            'data-surface="marketing"',
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ],
    )
    _check_not_contains(
        errors,
        "templates/marketing/base_marketing.html",
        [
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
        ],
    )

    # Control-plane shell: explicit surface + shell css; no marketing shell css.
    _check_contains(
        errors,
        "templates/control_plane_skeleton.html",
        [
            'data-surface="control-plane"',
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
        ],
    )
    _check_not_contains(
        errors,
        "templates/control_plane_skeleton.html",
        [
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ],
    )

    # Tenant base shell: design-system css present, no control-plane or marketing shell css.
    _check_contains(
        errors,
        "templates/base.html",
        [
            "css/design-system-unified.css",
            "css/platform-responsive-touch.css",
        ],
    )
    _check_not_contains(
        errors,
        "templates/base.html",
        [
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ],
    )

    # Portal / backend / Studio canvas: extends chain for most tenant app chrome (Studio uses portal_base).
    _check_contains(
        errors,
        "templates/portal_base.html",
        [
            'data-surface="tenant"',
            "css/design-system-unified.css",
            "css/platform-responsive-touch.css",
        ],
    )
    _check_not_contains(
        errors,
        "templates/portal_base.html",
        [
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ],
    )

    # Studio OS shell: extends tenant spine; forbid cross-surface CSS in shell partials.
    _check_file_exists(errors, "templates/studio_os/shell.html")
    _check_contains(
        errors,
        "templates/studio_os/shell.html",
        ['{% extends "portal_base.html" %}'],
    )
    for rel in (
        "templates/studio_os/shell.html",
        "templates/studio_os/partials/shell_extrastyle.html",
    ):
        _check_not_contains(
            errors,
            rel,
            [
                "css/control-plane-primary-nav.css",
                "css/control-plane-phase1-shell.css",
                "marketing/css/tokens-marketing.css",
                "marketing/css/marketing-shell.css",
            ],
        )

    # Admin bridge contracts on manager host.
    _check_contains(
        errors,
        "templates/admin/base_site.html",
        [
            "components/admin_nav_bridge.html",
            "partials/cp_context_drawer_shell.html",
            "js/authenticated-shell-manager.js",
        ],
    )

    if errors:
        print("verify_shell_architecture_matrix: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_shell_architecture_matrix: PASS "
        "(marketing/control-plane/admin/tenant base+portal+studio_os shell contracts)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
