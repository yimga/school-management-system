#!/usr/bin/env python3
"""
§0.4 LMS / SSO & federation — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links SAML/OIDC modules, federation health, federation tests, pre_deploy slice,
and external backlog for Clever/ClassLink sign-off.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = ROOT / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"

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


def main() -> int:
    errors: list[str] = []
    if not NORTH_STAR.is_file():
        errors.append(f"Missing {NORTH_STAR.relative_to(ROOT)}")
        return _fail(errors)

    text = NORTH_STAR.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{NORTH_STAR.relative_to(ROOT)} missing required LMS/SSO anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_lms_sso_doc_discipline: PASS "
        f"({NORTH_STAR.relative_to(ROOT)} LMS/SSO contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_lms_sso_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
