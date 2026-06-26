#!/usr/bin/env python3
"""Audit immersive login + auth panels for clip/hidden overflow regressions."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGIN_CSS = ROOT / "static/css/auth-login-canvas.css"
LOGIN_HTML = ROOT / "templates/auth/login.html"

GLASS_BLOCK_RE = re.compile(
    r"\.rmc-auth-immersive__glass\s*\{([^}]+)\}",
    re.DOTALL,
)
AUTH_BLOCK_RE = re.compile(
    r"\.rmc-auth-immersive__auth\s*\{([^}]+)\}",
    re.DOTALL,
)

FORBIDDEN_IN_GLASS = (
    "overflow: hidden",
    "overflow:hidden",
    "max-height: calc(100dvh",
)

REQUIRED_IN_AUTH = (
    "overflow-y: auto",
    "overflow-y:auto",
)


def audit() -> list[str]:
    failures: list[str] = []

    if not LOGIN_CSS.is_file():
        return ["missing static/css/auth-login-canvas.css"]

    css = LOGIN_CSS.read_text(encoding="utf-8")

    glass_match = GLASS_BLOCK_RE.search(css)
    if not glass_match:
        failures.append("auth-login-canvas.css: missing .rmc-auth-immersive__glass rule")
    else:
        glass_body = glass_match.group(1)
        for needle in FORBIDDEN_IN_GLASS:
            if needle in glass_body.replace(" ", ""):
                failures.append(
                    f"auth-login-canvas.css: .rmc-auth-immersive__glass must not use {needle!r} (clips role picker)"
                )
        if "overflow: visible" not in glass_body and "overflow:visible" not in glass_body.replace(
            " ", ""
        ):
            if "overflow-y: auto" not in glass_body and "overflow-y:auto" not in glass_body.replace(
                " ", ""
            ):
                failures.append(
                    "auth-login-canvas.css: .rmc-auth-immersive__glass must allow visible content or scroll"
                )

    auth_match = AUTH_BLOCK_RE.search(css)
    if not auth_match:
        failures.append("auth-login-canvas.css: missing .rmc-auth-immersive__auth rule")
    else:
        auth_body = auth_match.group(1).replace(" ", "")
        if not any(req.replace(" ", "") in auth_body for req in REQUIRED_IN_AUTH):
            failures.append(
                "auth-login-canvas.css: .rmc-auth-immersive__auth must scroll (overflow-y: auto)"
            )

    if LOGIN_HTML.is_file():
        html = LOGIN_HTML.read_text(encoding="utf-8")
        if "auth-login-canvas.css" not in html:
            failures.append("templates/auth/login.html: missing auth-login-canvas.css link")
        if 'include "components/next_action_strip.html"' in html:
            failures.append("templates/auth/login.html: next_action_strip must not render on login")
        if "rmc-auth-immersive__role-list" not in html:
            failures.append("templates/auth/login.html: missing role list markup")
        if "rmc-auth-immersive__role-row-chev" not in html:
            failures.append("templates/auth/login.html: missing role row chevron (right-edge affordance)")
        wow_markers = (
            ("data-rmc-auth-immersive", "immersive root data attribute"),
            ('include "auth/partials/login_immersive_canvas.html"', "login canvas partial"),
            ("rmc-auth-immersive__canvas", "hero canvas column"),
            ("rmc-auth-login-immersive.js", "immersive login behavior script"),
            ("LOGIN_IMMERSIVE", "immersive context wiring"),
        )
        for needle, label in wow_markers:
            if needle not in html:
                failures.append(f"templates/auth/login.html: missing WOW login marker — {label}")

    manager_login = ROOT / "templates/auth/manager_login.html"
    if manager_login.is_file():
        mgr = manager_login.read_text(encoding="utf-8")
        if "rmc-auth-immersive__role-list" in mgr:
            failures.append(
                "templates/auth/manager_login.html: operator login must not ship tenant role picker"
            )

    views_py = ROOT / "apps/accounts/views.py"
    if views_py.is_file():
        src = views_py.read_text(encoding="utf-8")
        if "use_operator_login_template" not in src:
            failures.append("apps/accounts/views.py: missing use_operator_login_template gate")
        if (
            '"auth/manager_login.html" if operator_login_surface else "auth/login.html"'
            not in src
        ):
            failures.append(
                "apps/accounts/views.py: tenant WOW login template must be default when not operator"
            )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    failures = audit()
    payload = {
        "surface": "auth-immersive-login",
        "finding_count": len(failures),
        "findings": failures,
    }

    if args.json or args.write:
        out = json.dumps(payload, indent=2)
        if args.write:
            dest = ROOT / "docs/generated/auth_immersive_clip_audit.json"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(out + "\n", encoding="utf-8")
        if args.json:
            print(out)

    if failures:
        print("FAIL: auth immersive clip integrity", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK: auth immersive clip integrity — role panel renders without glass clip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
