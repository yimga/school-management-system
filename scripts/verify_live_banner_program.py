#!/usr/bin/env python3
"""Live Banner Studio program gate — phases 1-4 scaffold + wiring checks."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    findings: list[str] = []

    program = ROOT / "apps/siteconfig/cockpit_live_banner_program.py"
    if not program.is_file():
        findings.append("missing apps/siteconfig/cockpit_live_banner_program.py")
    else:
        body = program.read_text(encoding="utf-8", errors="replace")
        for symbol in (
            "LIVE_BANNER_SOURCE_REGISTRY",
            "resolve_sources_enabled",
            "resolve_active_announcements",
            "compose_live_banner_cards",
            "suggest_live_banner_program",
            "draft_emergency_announcement",
        ):
            if symbol not in body:
                findings.append(f"cockpit_live_banner_program.py missing {symbol}")

    realdata = _text("apps/siteconfig/cockpit_activity_ticker_realdata.py")
    if "sources_enabled_from_payload" not in realdata:
        findings.append("realdata resolver missing sources_enabled_from_payload wiring")

    forms = _text("apps/siteconfig/forms_cockpit.py")
    for field in (
        "LIVE_BANNER_STUDIO_FIELDS",
        "atk_manager_sources",
        "atk_tenant_sources",
        "atk_manager_announcements",
        "atk_tenant_announcements",
        "_parse_live_banner_announcements",
    ):
        if field not in forms:
            findings.append(f"forms_cockpit.py missing {field}")

    template = _text("templates/siteconfig/super/cockpit_configure.html")
    if "live-banner-studio" not in template:
        findings.append("cockpit_configure.html missing live banner studio fieldset")
    if "live_banner_studio_fields" not in template:
        findings.append("cockpit_configure.html missing live_banner_studio_fields loop")

    preview = ROOT / "templates/partials/cockpit/_live_banner_studio_preview.html"
    if not preview.is_file():
        findings.append("missing partials/cockpit/_live_banner_studio_preview.html")

    js = ROOT / "static/js/rmc-live-banner-studio.js"
    if not js.is_file():
        findings.append("missing static/js/rmc-live-banner-studio.js")

    views = ROOT / "apps/siteconfig/views_live_banner_studio.py"
    if not views.is_file():
        findings.append("missing apps/siteconfig/views_live_banner_studio.py")

    urls = _text("apps/siteconfig/urls.py")
    for name in ("live_banner_suggest_program", "live_banner_draft_emergency"):
        if name not in urls:
            findings.append(f"siteconfig urls missing {name}")

    tests = ROOT / "apps/siteconfig/tests/test_cockpit_live_banner_program.py"
    if not tests.is_file():
        findings.append("missing apps/siteconfig/tests/test_cockpit_live_banner_program.py")

    try:
        from apps.siteconfig.cockpit_live_banner_program import LIVE_BANNER_SOURCE_REGISTRY

        if len(LIVE_BANNER_SOURCE_REGISTRY) < 10:
            findings.append(
                f"LIVE_BANNER_SOURCE_REGISTRY too small ({len(LIVE_BANNER_SOURCE_REGISTRY)})"
            )
    except Exception as exc:  # noqa: BLE001
        findings.append(f"unable to import LIVE_BANNER_SOURCE_REGISTRY: {exc}")

    if findings:
        print("verify_live_banner_program: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_live_banner_program: LIVE_BANNER_PROGRAM_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
