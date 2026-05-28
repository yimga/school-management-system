#!/usr/bin/env python3
"""CEZGP batch 1517 — parent identity UX gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    views_parent = ROOT / "apps/portal/views_parent.py"
    parent_identity = ROOT / "apps/portal/parent_identity.py"
    settings_tpl = ROOT / "templates/parent/settings_security.html"
    flags = ROOT / "apps/siteconfig/models_support.py"
    tests = ROOT / "apps/portal/tests/test_parent_guardian_switcher.py"
    settings_py = ROOT / "config/settings.py"

    for path in (views_parent, parent_identity, settings_tpl, flags, tests):
        if not path.is_file():
            findings.append(f"missing {path.relative_to(ROOT)}")

    if views_parent.is_file():
        body = views_parent.read_text(encoding="utf-8")
        if "parent_simplified_default" not in body:
            findings.append("views_parent.py missing parent_simplified_default")
        if "resolve_parent_simplified_default" not in body:
            findings.append("views_parent.py missing resolve_parent_simplified_default")

    if parent_identity.is_file():
        body = parent_identity.read_text(encoding="utf-8")
        if "school_membership_switch" not in body:
            findings.append("parent_identity.py missing school_membership_switch")

    if settings_tpl.is_file() and "passkey" not in settings_tpl.read_text(encoding="utf-8").lower():
        findings.append("settings_security.html missing passkey CTA")

    if flags.is_file() and "parent_simplified_default_home" not in flags.read_text(encoding="utf-8"):
        findings.append("models_support missing parent_simplified_default_home flag")

    if settings_py.is_file() and "parent_identity_ux" not in settings_py.read_text(encoding="utf-8"):
        findings.append("settings.py missing parent_identity_ux context processor")

    portal_base = ROOT / "templates/portal_base.html"
    login_tpl = ROOT / "templates/auth/login.html"
    accounts_urls = ROOT / "apps/accounts/urls.py"
    if portal_base.is_file() and "guardian_student_links.html" not in portal_base.read_text(encoding="utf-8"):
        findings.append("portal_base missing guardian_student_links include")
    if parent_identity.is_file() and "guardian_student_links_chrome" not in parent_identity.read_text(encoding="utf-8"):
        findings.append("parent_identity.py missing guardian_student_links_chrome")
    if accounts_urls.is_file() and 'name="password_reset"' not in accounts_urls.read_text(encoding="utf-8"):
        findings.append("accounts/urls.py missing password_reset route")
    if login_tpl.is_file() and "data-rmc-parent-password-reset" not in login_tpl.read_text(encoding="utf-8"):
        findings.append("login.html missing parent password reset CTA")

    if findings:
        print("verify_parent_identity_ux: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_parent_identity_ux: PARENT_IDENTITY_UX_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
