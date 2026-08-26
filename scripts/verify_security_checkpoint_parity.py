#!/usr/bin/env python3
"""Verify security checkpoint parity across MFA + auth-shell + security hub surfaces."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKPOINT_CSS = "css/rmc-mfa-checkpoint.css"
CHECKPOINT_OTP_JS = "js/rmc-mfa-otp.js"

FULL_PAGE_MANIFEST: tuple[tuple[str, str | None], ...] = (
    ("templates/accounts/mfa_verify.html", "verify"),
    ("templates/accounts/mfa_setup.html", "setup"),
    ("templates/accounts/mfa_verify_manager.html", "verify"),
    ("templates/accounts/mfa_setup_manager.html", "setup"),
    ("templates/accounts/password_change_form.html", "password"),
    ("templates/accounts/password_change_done.html", "password"),
    ("templates/accounts/legacy_setup.html", "onboarding"),
    ("templates/accounts/guardian_setup.html", "invite"),
    ("templates/accounts/claim_invite.html", "invite"),
    ("templates/accounts/magic_link_request.html", "verify"),
    ("templates/accounts/join_school.html", "invite"),
    ("templates/accounts/onboarding_profile.html", "onboarding"),
    ("templates/accounts/security_posture_review.html", "password"),
    ("templates/accounts/sessions_page.html", "password"),
    ("templates/accounts/security_trust_hub.html", "password"),
    ("templates/accounts/tenant_staff_invite_accept.html", "invite"),
    ("templates/accounts/operator_invite_accept.html", "invite"),
    ("templates/accounts/owner_onboarding/account.html", "onboarding"),
    ("templates/accounts/owner_onboarding/school.html", "onboarding"),
    ("templates/accounts/owner_onboarding/done.html", "onboarding"),
    ("templates/registration/password_reset_form.html", "reset"),
    ("templates/registration/password_reset_done.html", "reset"),
    ("templates/registration/password_reset_confirm.html", "reset"),
    ("templates/registration/password_reset_complete.html", "reset"),
    ("templates/auth/school_picker.html", "onboarding"),
    ("templates/schools/signup_school.html", "onboarding"),
    ("templates/schools/signup_school_done.html", "onboarding"),
    ("templates/schools/verify_signup.html", "onboarding"),
    ("templates/schools/resend_verification.html", "onboarding"),
    ("templates/schools/onboard_wizard.html", "onboarding"),
    ("templates/schools/accept_invite.html", "invite"),
    ("templates/parent/settings_security.html", "password"),
    ("templates/parent/claim_invite.html", "invite"),
    ("templates/errors/401.html", "verify"),
    ("templates/schools/global_login_discovery.html", "onboarding"),
)

PARTIAL_MANIFEST: tuple[tuple[str, str], ...] = (
    ("templates/accounts/partials/mfa_verify_page_body.html", "mfa-verify"),
    ("templates/accounts/partials/mfa_setup_page_body.html", "mfa-setup"),
    ("templates/accounts/partials/_mfa_setup_wizard_inline.html", "mfa-setup-inline"),
    ("templates/accounts/partials/operator_security_posture_review_body.html", "security-posture-operator"),
)

# Immersive login surfaces — exempt from checkpoint wrap (dedicated auth-login-canvas.css).
IMMERSIVE_EXEMPT: frozenset[str] = frozenset(
    {
        "templates/auth/login.html",
    }
)

# Control-plane login — strip forbidden; dedicated manager-login.css (no checkpoint wrap).
CP_LOGIN_STRIP_ONLY: frozenset[str] = frozenset(
    {
        "templates/auth/manager_login.html",
        "templates/auth/admin_login.html",
    }
)

FORBIDDEN_MARKERS = (
    "rmc-account-auth-shell__rail",
    'include "components/next_action_strip.html"',
)

REQUIRED_AUTH_SHELL_MARKERS = (
    "security_checkpoint_page_open.html",
    "security_checkpoint_page_close.html",
    CHECKPOINT_CSS,
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _static_exists(static_rel: str) -> bool:
    return (ROOT / "static" / static_rel).is_file()


def audit() -> list[str]:
    failures: list[str] = []

    for static_rel in (CHECKPOINT_CSS, CHECKPOINT_OTP_JS):
        if not _static_exists(static_rel):
            failures.append(f"missing static asset: static/{static_rel}")

    for rel, _flow in FULL_PAGE_MANIFEST:
        if not (ROOT / rel).is_file():
            failures.append(f"missing template: {rel}")
            continue
        text = _read(rel)
        if CHECKPOINT_CSS not in text:
            failures.append(f"{rel}: missing {CHECKPOINT_CSS} link")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                failures.append(f"{rel}: forbidden marker {marker!r}")
        if "security_checkpoint_page_open" in text or "auth-shell" in text:
            for marker in REQUIRED_AUTH_SHELL_MARKERS:
                if marker not in text:
                    failures.append(f"{rel}: missing auth-shell contract {marker!r}")

    for rel in CP_LOGIN_STRIP_ONLY:
        if not (ROOT / rel).is_file():
            failures.append(f"missing template: {rel}")
            continue
        if 'include "components/next_action_strip.html"' in _read(rel):
            failures.append(f"{rel}: forbidden next_action_strip on CP login")

    for rel, checkpoint_id in PARTIAL_MANIFEST:
        if not (ROOT / rel).is_file():
            failures.append(f"missing partial: {rel}")
            continue
        text = _read(rel)
        if "data-rmc-security-checkpoint" not in text:
            failures.append(f"{rel}: missing data-rmc-security-checkpoint")
        for marker in FORBIDDEN_MARKERS:
            if marker in text:
                failures.append(f"{rel}: forbidden marker {marker!r}")

    for rel in (
        "templates/accounts/partials/mfa_verify_page_body.html",
        "templates/accounts/partials/mfa_setup_page_body.html",
    ):
        if "security_checkpoint_otp.html" not in _read(rel):
            failures.append(f"{rel}: must include security_checkpoint_otp.html")

    # profile must not duplicate next_action_strip (shell may still inject via block)
    profile = ROOT / "templates/accounts/profile.html"
    if profile.is_file() and 'include "components/next_action_strip.html"' in _read(
        "templates/accounts/profile.html"
    ):
        failures.append("templates/accounts/profile.html: forbidden inline next_action_strip")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    failures = audit()
    payload = {
        "surface_count": len(FULL_PAGE_MANIFEST) + len(PARTIAL_MANIFEST),
        "full_page_templates": [r for r, _ in FULL_PAGE_MANIFEST],
        "partial_templates": [r for r, _ in PARTIAL_MANIFEST],
        "immersive_exempt": sorted(IMMERSIVE_EXEMPT),
        "cp_login_strip_only": sorted(CP_LOGIN_STRIP_ONLY),
        "finding_count": len(failures),
        "findings": failures,
    }

    if args.json or args.write:
        out = json.dumps(payload, indent=2)
        if args.write:
            dest = ROOT / "docs/generated/security_checkpoint_surface_audit.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(out + "\n", encoding="utf-8")
        if args.json:
            print(out)

    if failures:
        print("FAIL: security checkpoint parity", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"OK: security checkpoint parity — {payload['surface_count']} surfaces, 0 findings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
