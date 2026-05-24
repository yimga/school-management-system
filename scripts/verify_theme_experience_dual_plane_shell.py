#!/usr/bin/env python3
"""Verify dual-plane theme bundle is wired into all authenticated shells (load-last)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "static/css/rmc-theme-experience-dual-plane.css"
MARKER = "rmc-theme-experience-dual-plane.css"
PARTIAL = "rmc_theme_experience_dual_plane_styles.html"
PASS = "THEME_EXPERIENCE_DUAL_PLANE_SHELL_PASS"

SHELLS = (
    "templates/base.html",
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/admin/base_site.html",
    "templates/admin/login.html",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _dual_plane_index(text: str) -> int:
    return max(
        text.rfind(MARKER),
        text.rfind(PARTIAL),
    )


def main() -> int:
    errors: list[str] = []

    if not CSS.is_file():
        errors.append(f"missing {CSS.relative_to(ROOT)}")
    else:
        css = _read(CSS)
        for token in (
            "--rmc-chrome-plane",
            "data-rmc-host-kind=\"tenant\"",
            "data-rmc-host-kind=\"manager\"",
            "marketing-surface",
            "[data-rmc-authenticated-shell]",
            "body.backend-shell",
            "body.control-plane-shell .rmc-app-shell__header",
            "html[data-theme=\"dark\"] body.control-plane-shell .rmc-app-shell__canvas",
            "body.portal-body-with-layout:not(.control-plane-shell)",
            ".cp-primary-nav__pill--active",
            "html[data-surface=\"tenant\"] body.base-document-shell",
            ".cp-header .cp-topbar-search-input",
            ".bg-light",
            ".rmc-civic-footer a:hover",
        ):
            if token not in css:
                errors.append(f"dual-plane CSS missing marker: {token}")

    partial = ROOT / "templates/partials/rmc_theme_experience_dual_plane_styles.html"
    tail = ROOT / "templates/partials/rmc_authenticated_theme_tail.html"
    partial_src = _read(partial)
    if MARKER not in partial_src and "rmc_authenticated_theme_tail.html" not in partial_src:
        errors.append("partial missing stylesheet link")
    if MARKER not in _read(tail):
        errors.append("authenticated theme tail missing stylesheet link")

    for rel in SHELLS:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing shell: {rel}")
            continue
        text = _read(path)
        if MARKER not in text and PARTIAL not in text:
            errors.append(f"{rel} missing dual-plane include/link")
            continue
        idx = _dual_plane_index(text)
        if "theme-platform-contrast.css" in text:
            contrast_idx = text.rfind("theme-platform-contrast.css")
            if idx < contrast_idx:
                errors.append(f"{rel}: dual-plane must load after theme-platform-contrast.css")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print(PASS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
