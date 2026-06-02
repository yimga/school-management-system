#!/usr/bin/env python3
"""Operator control-plane header (v8 stacked + LIVE ticker) and civic footer parity."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

OPERATOR_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/control_plane_base.html",
    "templates/portal_base.html",
    "templates/admin/base.html",
)

ERROR_CP_PAGES = (
    "templates/errors/404_control_plane.html",
    "templates/errors/403_control_plane.html",
    "templates/errors/500_control_plane.html",
    "templates/errors/503_control_plane.html",
)

LOGIN_SUPPRESS_HEADER = (
    "templates/auth/manager_login.html",
    "templates/auth/admin_login.html",
)


def main() -> int:
    errors: list[str] = []

    skel = (ROOT / "templates/control_plane_skeleton.html").read_text(encoding="utf-8")
    if "control_plane_unified_header.html" not in skel:
        errors.append("skeleton: missing default control_plane_unified_header")
    if "rmc_operator_footer_civic.html" not in skel:
        errors.append("skeleton: missing rmc_operator_footer_civic")
    if "rmc-footer-notebook-anchor" in skel:
        errors.append("skeleton: footer notebook dock must not be present")

    unified = (ROOT / "templates/partials/control_plane_unified_header.html").read_text(
        encoding="utf-8"
    )
    if "cockpit/_activity_ticker.html" not in unified:
        errors.append("unified header: missing full LIVE ticker row")
    if 'cp-header__row--live' not in unified:
        errors.append("unified header: missing cp-header__row--live")

    civic = (ROOT / "templates/partials/rmc_operator_footer_civic.html").read_text(
        encoding="utf-8"
    )
    if 'data-rmc-footer-surface="operator-civic"' not in civic:
        errors.append("civic footer: missing operator-civic surface marker")
    if "cp-footer-ribbon--secondary" not in civic:
        errors.append("civic footer: missing secondary ribbon")

    for rel in ("templates/portal_base.html", "templates/admin/base.html"):
        body = (ROOT / rel).read_text(encoding="utf-8")
        if "rmc_operator_footer_compact.html" in body and "manager_login" not in rel:
            errors.append(f"{rel}: still references compact footer (use civic)")
        if rel == "templates/portal_base.html" and "control_plane_unified_header.html" not in body:
            errors.append(f"{rel}: missing unified header on manager bridge")

    for rel in LOGIN_SUPPRESS_HEADER:
        body = (ROOT / rel).read_text(encoding="utf-8")
        if "block cp_shell_header %}{% endblock" not in body.replace(" ", ""):
            if "{% block cp_shell_header %}{% endblock %}" not in body:
                errors.append(f"{rel}: login must suppress default CP header")

    for rel in ERROR_CP_PAGES:
        body = (ROOT / rel).read_text(encoding="utf-8")
        if 'block cp_shell_header' in body:
            errors.append(f"{rel}: should inherit skeleton default header, not override")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("OK: operator CP header/footer parity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
