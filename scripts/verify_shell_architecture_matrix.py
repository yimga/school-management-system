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

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify shell architecture matrix contracts."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _read(root: Path, rel_path: str) -> str:
    return (root / rel_path).read_text(encoding="utf-8", errors="replace")


def _check_contains(
    errors: list[str], root: Path, rel_path: str, must_include: list[str]
) -> None:
    text = _read(root, rel_path)
    for token in must_include:
        if token not in text:
            errors.append(f"{rel_path} missing required token: {token!r}")


def _check_not_contains(
    errors: list[str], root: Path, rel_path: str, must_not_include: list[str]
) -> None:
    text = _read(root, rel_path)
    for token in must_not_include:
        if token in text:
            errors.append(f"{rel_path} contains forbidden token: {token!r}")


def _portal_base_tenant_surface_ok(text: str) -> bool:
    """portal_base sets tenant surface on tenant hosts via {% if manager %}…{% else %}tenant."""
    if 'data-surface="tenant"' in text:
        return True
    return 'data-surface="{%' in text and "tenant{%" in text


def _portal_base_cp_css_manager_only(text: str, token: str) -> bool:
    """Control-plane shell CSS may load only inside manager-host {% if %} blocks."""
    idx = text.find(token)
    if idx < 0:
        return True
    window = text[max(0, idx - 800) : idx]
    return "public_host_kind == 'manager'" in window or 'public_host_kind == "manager"' in window


def _check_file_exists(errors: list[str], root: Path, rel_path: str) -> None:
    if not (root / rel_path).is_file():
        errors.append(f"missing required file: {rel_path}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_shell_architecture_matrix: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    # Canonical architecture doc + core nav tests should stay present.
    _check_file_exists(errors, root, "docs/SHELL_ARCHITECTURE_MATRIX.md")
    _check_contains(
        errors,
        root,
        "docs/SHELL_ARCHITECTURE_MATRIX.md",
        [
            "verify_shell_architecture_matrix.py",
            "Duplicate-bundle sweep",
            "Repository audit log",
            "Staging / production URL matrix",
            "Operator sign-off log",
        ],
    )
    _check_file_exists(errors, root, "docs/PHASE_H_MANUAL_CHECKLIST.md")
    _check_contains(
        errors,
        root,
        "docs/PHASE_H_MANUAL_CHECKLIST.md",
        [
            "verify_shell_architecture_matrix.py",
            "Phase H",
        ],
    )
    _check_file_exists(errors, root, "apps/schools/tests/test_primary_control_plane_nav.py")
    _check_file_exists(errors, root, "apps/schools/tests/test_control_plane_nav_roles.py")

    # Marketing shell: marketing marker + marketing css; no control-plane shell css.
    _check_contains(
        errors,
        root,
        "templates/marketing/base_marketing.html",
        [
            'data-surface="marketing"',
            "marketing/css/marketing-critical.min.css",
            "marketing/css/marketing-enhanced.min.css",
        ],
    )
    _check_not_contains(
        errors,
        root,
        "templates/marketing/base_marketing.html",
        [
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
        ],
    )

    # Control-plane shell: explicit surface + shell css; no marketing shell css.
    _check_contains(
        errors,
        root,
        "templates/control_plane_skeleton.html",
        [
            'data-surface="control-plane"',
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
        ],
    )
    _check_not_contains(
        errors,
        root,
        "templates/control_plane_skeleton.html",
        [
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ],
    )

    # Tenant base shell: design-system css present, no control-plane or marketing shell css.
    _check_contains(
        errors,
        root,
        "templates/base.html",
        [
            "css/design-system-unified.css",
            "css/platform-responsive-touch.css",
        ],
    )
    _check_not_contains(
        errors,
        root,
        "templates/base.html",
        [
            "css/control-plane-primary-nav.css",
            "css/control-plane-phase1-shell.css",
            "marketing/css/tokens-marketing.css",
            "marketing/css/marketing-shell.css",
        ],
    )

    # Portal / backend / Studio canvas: extends chain for most tenant app chrome (Studio uses portal_base).
    portal_text = _read(root, "templates/portal_base.html")
    if not _portal_base_tenant_surface_ok(portal_text):
        errors.append(
            'templates/portal_base.html missing required tenant surface marker '
            '(data-surface="tenant" or {% else %}tenant{% endif %})'
        )
    for token in (
        "css/design-system-unified.css",
        "css/platform-responsive-touch.css",
    ):
        if token not in portal_text:
            errors.append(f"templates/portal_base.html missing required token: {token!r}")
    for forbidden in (
        "css/control-plane-primary-nav.css",
        "css/control-plane-phase1-shell.css",
        "marketing/css/tokens-marketing.css",
        "marketing/css/marketing-shell.css",
    ):
        if forbidden in portal_text and not _portal_base_cp_css_manager_only(
            portal_text, forbidden
        ):
            errors.append(
                f"templates/portal_base.html contains forbidden token outside "
                f"manager-host block: {forbidden!r}"
            )

    # Studio OS shell: extends tenant spine; forbid cross-surface CSS in shell partials.
    _check_file_exists(errors, root, "templates/studio_os/shell.html")
    _check_contains(
        errors,
        root,
        "templates/studio_os/shell.html",
        ['{% extends "portal_base.html" %}'],
    )
    for rel in (
        "templates/studio_os/shell.html",
        "templates/studio_os/partials/shell_extrastyle.html",
    ):
        _check_not_contains(
            errors,
            root,
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
        root,
        "templates/admin/base_site.html",
        [
            "components/admin_nav_bridge.html",
            "partials/cp_context_drawer_shell.html",
            "js/authenticated-shell-manager.js",
        ],
    )

    if errors:
        print("verify_shell_architecture_matrix:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_shell_architecture_matrix: PASS "
        "(marketing/control-plane/admin/tenant base+portal+studio_os shell contracts)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
