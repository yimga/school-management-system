#!/usr/bin/env python3
"""
§0.4 LMS / SSO & federation — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links SAML/OIDC modules, federation health, federation tests, pre_deploy slice,
and external backlog for Clever/ClassLink sign-off.

Usage: python scripts/verify_lms_sso_doc_discipline.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

_REQUIRED = (
    "LMS / SSO and federation",
    "LMS / SSO (operator contract",
    "apps/accounts/views_saml.py",
    "apps/accounts/views_oidc.py",
    "apps/accounts/federation_sso_health.py",
    "refresh_saml_idp_metadata",
    "apps/accounts/tests/test_saml_views.py",
    "apps/accounts/tests/test_federation_sso_health.py",
    "apps.accounts.tests.test_federation_sso_health",
    "scripts/pre_deploy_gate.sh",
    "SOT_REMAINING_ITEMS_BACKLOG.md",
    "Clever",
    "ClassLink",
    "verify_lms_sso_doc_discipline.py",
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NORTH_STAR LMS/SSO doc anchors (§0.4)."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_lms_sso_doc_discipline: {exc}", file=sys.stderr)
        return 1

    north_star = root / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"
    errors: list[str] = []
    if not north_star.is_file():
        errors.append(f"Missing {north_star.relative_to(root)}")
        return _fail(errors)

    text = north_star.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{north_star.relative_to(root)} missing required LMS/SSO anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_lms_sso_doc_discipline: PASS "
        f"({north_star.relative_to(root)} LMS/SSO contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_lms_sso_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
