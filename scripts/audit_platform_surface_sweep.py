#!/usr/bin/env python3
"""Platform-wide surface sweep — auth checkpoints, security hubs, sparse layouts."""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

CHECKPOINT_CSS = "rmc-mfa-checkpoint.css"
CHECKPOINT_OPEN = "security_checkpoint_page_open.html"

# Paths scanned for auth/security checkpoint contract.
AUTH_SECURITY_GLOBS = (
    "accounts/**/*.html",
    "auth/**/*.html",
    "registration/**/*.html",
    "schools/signup*.html",
    "schools/verify_signup.html",
    "schools/resend_verification.html",
    "schools/onboard_wizard.html",
    "schools/accept_invite.html",
    "parent/settings_security.html",
    "parent/claim_invite.html",
    "errors/401.html",
    "portal/mfa_policy.html",
    "marketing/global_discovery.html",
    "schools/global_login_discovery.html",
)

SPARSE_VOID_RE = re.compile(
    r'class="[^"]*\bcontainer\b[^"]*py-5\b[^"]*"[^>]*>\s*'
    r'<div class="row justify-content-center">\s*'
    r'<div class="col-(?:md-6|lg-6)"',
    re.MULTILINE,
)

AUTH_SHELL_RE = re.compile(r'\bauth-shell\b')
STRIP_RE = re.compile(r'include\s+"components/next_action_strip\.html"')


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _collect_auth_templates() -> list[Path]:
    found: set[Path] = set()
    for pattern in AUTH_SECURITY_GLOBS:
        for p in TEMPLATES.glob(pattern):
            if p.is_file():
                found.add(p)
    return sorted(found, key=lambda p: _rel(p))


def audit() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []

    for path in _collect_auth_templates():
        rel = _rel(path)
        text = path.read_text(encoding="utf-8", errors="replace")

        if rel == "templates/auth/login.html":
            if CHECKPOINT_CSS not in text and "auth-login-canvas.css" not in text:
                findings.append(
                    {
                        "severity": "high",
                        "file": rel,
                        "issue": "login missing immersive or checkpoint CSS",
                    }
                )
            continue

        if rel in {
            "templates/auth/manager_login.html",
            "templates/auth/admin_login.html",
        }:
            if STRIP_RE.search(text):
                findings.append(
                    {
                        "severity": "medium",
                        "file": rel,
                        "issue": "CP login still includes next_action_strip",
                    }
                )
            continue

        is_security = any(
            k in path.name.lower()
            for k in (
                "mfa",
                "password_change",
                "password_reset",
                "security_posture",
                "security_trust",
                "sessions_page",
                "invite_accept",
                "claim_invite",
                "guardian_setup",
                "legacy_setup",
                "signup_school",
                "verify_signup",
                "resend_verification",
                "onboard_wizard",
                "accept_invite",
                "school_picker",
                "global_login_discovery",
                "global_discovery",
                "settings_security",
                "401.html",
                "owner_onboarding",
            )
        )
        if not is_security:
            continue

        if STRIP_RE.search(text):
            findings.append(
                {
                    "severity": "medium",
                    "file": rel,
                    "issue": "next_action_strip on auth/security page",
                }
            )

        if AUTH_SHELL_RE.search(text) and CHECKPOINT_OPEN not in text:
            if "/partials/" not in rel and "data-rmc-security-checkpoint-page" not in text:
                findings.append(
                    {
                        "severity": "high",
                        "file": rel,
                        "issue": "auth-shell without security_checkpoint_page_open",
                    }
                )

        needs_css = (
            CHECKPOINT_OPEN in text
            or "data-rmc-security-checkpoint-page" in text
            or (AUTH_SHELL_RE.search(text) and "/partials/" not in rel)
        )
        if needs_css and CHECKPOINT_CSS not in text and "/partials/" not in rel:
                findings.append(
                    {
                        "severity": "high",
                        "file": rel,
                        "issue": f"missing {CHECKPOINT_CSS}",
                    }
                )

        if SPARSE_VOID_RE.search(text):
            findings.append(
                {
                    "severity": "low",
                    "file": rel,
                    "issue": "sparse centered column (py-5 + col-md-6) — likely empty void",
                }
            )

        if "rmc-security-hub-grid" not in text and "data-rmc-surface-density" not in text:
            if rel.endswith("security_trust_hub.html") or rel.endswith(
                "settings_security.html"
            ):
                findings.append(
                    {
                        "severity": "medium",
                        "file": rel,
                        "issue": "security hub missing density grid contract",
                    }
                )

    return findings


def _audit_auth_clip_integrity() -> list[str]:
    script = ROOT / "scripts/audit_auth_immersive_clip_integrity.py"
    spec = importlib.util.spec_from_file_location("audit_auth_immersive_clip_integrity", script)
    if spec is None or spec.loader is None:
        return ["unable to load audit_auth_immersive_clip_integrity.py"]
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.audit()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    findings = audit()
    clip_failures = _audit_auth_clip_integrity()
    for msg in clip_failures:
        findings.append(
            {
                "severity": "high",
                "file": "static/css/auth-login-canvas.css",
                "issue": msg,
            }
        )
    payload = {
        "scanned_family": "auth-security-platform-sweep",
        "template_count": len(_collect_auth_templates()),
        "finding_count": len(findings),
        "findings": findings,
    }

    if args.json or args.write:
        out = json.dumps(payload, indent=2)
        if args.write:
            dest = ROOT / "docs/generated/platform_surface_sweep_audit.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(out + "\n", encoding="utf-8")
        if args.json:
            print(out)

    if findings:
        print("FAIL: platform surface sweep", file=sys.stderr)
        for f in findings:
            print(f"  [{f['severity']}] {f['file']}: {f['issue']}", file=sys.stderr)
        return 1

    print(
        f"OK: platform surface sweep — {payload['template_count']} templates, 0 findings"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
