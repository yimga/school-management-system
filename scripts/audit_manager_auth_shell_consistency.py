#!/usr/bin/env python3
"""Audit manager-host authentication/account pages for shell consistency."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8", errors="replace")


def static_audit() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    checks = {
        "templates/accounts/mfa_setup.html": [
            'extends "portal_base.html"',
            "accounts/partials/mfa_setup_page_body.html",
        ],
        "templates/accounts/mfa_verify.html": [
            'extends "base.html"',
            "accounts/partials/mfa_verify_page_body.html",
        ],
        "templates/accounts/mfa_setup_manager.html": [
            'extends "backend_base_manager.html"',
            "{% block backend_main %}",
            "accounts/partials/mfa_setup_page_body.html",
        ],
        "templates/accounts/mfa_verify_manager.html": [
            'extends "backend_base_manager.html"',
            "{% block backend_main %}",
            "accounts/partials/mfa_verify_page_body.html",
        ],
        "templates/accounts/profile.html": [
            'extends "backend_base.html"',
            "{% block backend_page %}",
            'data-rmc-balanced-profile="1"',
        ],
        "apps/accounts/views_mfa.py": [
            "def _mfa_template",
            'getattr(request, "public_host_kind", None) == "manager"',
            "_manager.",
        ],
        "static/css/manager-control-plane.css": [
            "manager-portal-bridge",
            "grid-template-columns: clamp(16rem, 18vw, 20rem) minmax(0, 1fr)",
            ".portal-resize-handle",
        ],
    }
    for rel_path, tokens in checks.items():
        text = _read(rel_path)
        for token in tokens:
            if token not in text:
                findings.append(
                    {
                        "severity": "high",
                        "file": rel_path,
                        "issue": f"missing manager shell contract token: {token}",
                    }
                )
    return findings


def render_audit() -> list[dict[str, str]]:
    import django
    from django.contrib.auth import get_user_model
    from django.test import Client, override_settings
    from django.urls import reverse

    django.setup()
    findings: list[dict[str, str]] = []
    host = "manager.runmycampus.com"
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="manager_auth_shell_audit",
        defaults={
            "email": "manager-auth-shell-audit@example.test",
            "is_staff": True,
            "is_superuser": True,
            "role": User.Role.SUPERADMIN,
        },
    )
    dirty_fields: list[str] = []
    for field, value in {
        "is_staff": True,
        "is_superuser": True,
        "role": User.Role.SUPERADMIN,
    }.items():
        if getattr(user, field) != value:
            setattr(user, field, value)
            dirty_fields.append(field)
    if not user.check_password("manager-auth-shell-pass"):
        user.set_password("manager-auth-shell-pass")
        dirty_fields.append("password")
    if dirty_fields:
        user.save(update_fields=sorted(set(dirty_fields)))

    with override_settings(
        ROOT_URLCONF="config.urls",
        ALLOWED_HOSTS=["*", host, "testserver"],
        SECURE_SSL_REDIRECT=False,
        SESSION_COOKIE_SECURE=False,
        CSRF_COOKIE_SECURE=False,
    ):
        client = Client(HTTP_HOST=host, raise_request_exception=False)
        client.force_login(user)
        session = client.session
        session["mfa_verified"] = True
        session["security_posture_review_nagged"] = True
        session["security_posture_review_ack"] = True
        session.save()
        try:
            from scripts._manager_render_smoke import prepare_manager_smoke_client

            prepare_manager_smoke_client(client)
        except Exception:
            pass

        route_checks = {
            "accounts:mfa_setup": {
                "required": [
                    'data-rmc-shell-body="control-plane-skeleton"',
                    'id="cp-main-content"',
                    'data-rmc-auth-manager-shell="mfa-setup"',
                ],
                "forbidden": ["manager-portal-bridge", "portal-resize-handle"],
            },
            "accounts:user_profile": {
                "required": [
                    'data-rmc-shell-body="control-plane-skeleton"',
                    'id="cp-main-content"',
                    'data-rmc-balanced-profile="1"',
                ],
                "forbidden": ["manager-portal-bridge", "portal-resize-handle"],
            },
        }
        for name, contract in route_checks.items():
            path = reverse(name)
            response = client.get(path)
            if response.status_code != 200:
                findings.append(
                    {
                        "severity": "high",
                        "route": path,
                        "issue": f"expected HTTP 200, got {response.status_code}",
                    }
                )
                continue
            html = response.content.decode("utf-8", errors="replace")
            for token in contract["required"]:
                if token not in html:
                    findings.append(
                        {
                            "severity": "high",
                            "route": path,
                            "issue": f"missing rendered token: {token}",
                        }
                    )
            for token in contract["forbidden"]:
                if token in html:
                    findings.append(
                        {
                            "severity": "medium",
                            "route": path,
                            "issue": f"forbidden legacy portal artifact rendered: {token}",
                        }
                    )
    return findings


def main() -> int:
    findings = static_audit()
    try:
        findings.extend(render_audit())
    except Exception as exc:
        findings.append(
            {
                "severity": "high",
                "issue": f"manager auth render audit failed: {exc}",
            }
        )

    out = {
        "finding_count": len(findings),
        "findings": findings,
    }
    out_path = ROOT / "docs" / "generated" / "manager_auth_shell_consistency_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if findings:
        print(f"MANAGER_AUTH_SHELL_CONSISTENCY_FAIL ({len(findings)} findings)")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("MANAGER_AUTH_SHELL_CONSISTENCY_PASS (manager auth/profile shell contracts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
