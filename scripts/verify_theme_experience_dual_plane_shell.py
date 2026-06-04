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
SW_MARKER = "sms-v4.01.46-dual-plane-theme-sweep3-2026-06-02"

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


def _check_v4_01_44_coherence(errors: list[str]) -> None:
    portal_path = ROOT / "templates/portal_base.html"
    portal = _read(portal_path)
    if "portal-sidebar-tone-light" in portal or "portal-sidebar-tone-dark" in portal:
        errors.append(
            "portal_base.html: portal-sidebar-tone-* body classes must not be SSR'd "
            "(resolved theme drives tenant sidebar via dual-plane CSS)"
        )
    if portal.count(PARTIAL) < 3:
        errors.append(
            f"portal_base.html: expected >=3 {PARTIAL} includes (head, deferred, terminal)"
        )
    skeleton = _read(ROOT / "templates/control_plane_skeleton.html")
    if skeleton.count(PARTIAL) < 2:
        errors.append(
            f"control_plane_skeleton.html: expected >=2 {PARTIAL} includes (head + terminal)"
        )
    base = _read(ROOT / "templates/base.html")
    if base.count(PARTIAL) < 2:
        errors.append(f"base.html: expected >=2 {PARTIAL} includes (head + terminal)")
    if "rmc-platform-vertical-compact.css" in base:
        compact_idx = base.rfind("rmc-platform-vertical-compact.css")
        dual_idx = base.rfind(PARTIAL)
        if dual_idx < compact_idx:
            errors.append("base.html: dual-plane must load after rmc-platform-vertical-compact.css in head")
    admin_site = _read(ROOT / "templates/admin/base_site.html")
    if admin_site.count(PARTIAL) < 2:
        errors.append(
            f"admin/base_site.html: expected >=2 {PARTIAL} includes (head + terminal)"
        )
    body_close = portal.rfind("</body>")
    last_partial = portal.rfind(PARTIAL)
    if body_close == -1 or last_partial == -1 or last_partial > body_close:
        errors.append("portal_base.html: missing terminal dual-plane include before </body>")
    elif body_close - last_partial > 800:
        errors.append(
            "portal_base.html: terminal dual-plane include too far from </body> "
            "(late CSS may override cascade)"
        )
    if "header_theme_chip" in portal:
        errors.append(
            "portal_base.html: theme chip must live in user_dropdown only, not shell header"
        )

    theme_js = _read(ROOT / "static/js/theme-preference-bootstrap.js")
    for token in (
        "shouldSyncPortalBackendPalette",
        "manager-portal-bridge",
        "control-plane-shell",
    ):
        if token not in theme_js:
            errors.append(f"theme-preference-bootstrap.js missing operator guard: {token}")

    topbar = _read(ROOT / "templates/partials/manager_operator_topbar.html")
    if "_activity_ticker_inline.html" not in topbar:
        errors.append("manager_operator_topbar.html: Tier-1 inline LIVE badge missing")
    if "header_theme_chip" in topbar:
        errors.append(
            "manager_operator_topbar.html: theme controls belong in user_dropdown, not header"
        )

    user_dd = _read(ROOT / "templates/components/user_dropdown.html")
    if "Appearance" not in user_dd:
        errors.append("user_dropdown.html: Appearance section missing")
    if 'theme_chip_layout="dropdown"' not in user_dd:
        errors.append("user_dropdown.html: header_theme_chip dropdown layout missing")

    sw = _read(ROOT / "static/js/service-worker.js")
    if SW_MARKER not in sw:
        errors.append(f"service-worker.js: expected CACHE_VERSION {SW_MARKER}")

    for rel, token in (
        ("static/css/design-tokens-luxury.css", "calc(72px * 1.1)"),
        ("static/css/rmc-platform-header.css", "calc(64px * 1.1)"),
    ):
        text = _read(ROOT / rel)
        if token not in text:
            errors.append(f"{rel}: platform header +10% height token missing")


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
            "manager-portal-bridge",
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
            "body.manager-portal-bridge .cp-sidebar-col",
            "body.manager-portal-bridge .page-wrap",
            "cp-header--consolidated",
            "html[data-resolved-theme=\"light\"] body.portal-body-with-layout",
            ".rmc-workflow-progress-strip",
            "v4.01.46",
            "operator-civic",
            "body.manager-portal-bridge.control-plane-shell",
            ".metric-card",
            ".activity-section",
            ".child-card",
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

    _check_v4_01_44_coherence(errors)

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print(PASS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
