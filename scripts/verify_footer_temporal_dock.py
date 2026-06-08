#!/usr/bin/env python3
"""Footer temporal dock — centered clock/weather chip on every dashboard footer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS_LOAD_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/portal_base.html",
    "templates/base.html",
    "templates/admin/base_site.html",
)

FOOTER_PARTIALS = (
    "templates/partials/rmc_operator_footer_civic.html",
    "templates/partials/rmc_operator_footer_compact.html",
    "templates/components/dashboard_footer.html",
)

DOCK_PARTIAL = "templates/partials/cockpit/_footer_temporal_dock.html"
DOCK_CSS = "static/css/rmc-footer-temporal-dock.css"
WIDGET = "templates/components/header_weather_widget.html"


def _read(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    errors: list[str] = []

    for rel in CSS_LOAD_SHELLS:
        if "rmc-footer-temporal-dock.css" not in _read(rel):
            errors.append(f"{rel}: missing rmc-footer-temporal-dock.css")

    for rel in FOOTER_PARTIALS:
        if DOCK_PARTIAL.split("/")[-1] not in _read(rel):
            errors.append(f"{rel}: missing _footer_temporal_dock.html include")

    css = _read(DOCK_CSS)
    for needle in (
        "operator-compact",
        "pointer-events: auto",
        "z-index: 3",
        "overflow: visible",
        "translate(-50%, -50%)",
    ):
        if needle not in css:
            errors.append(f"{DOCK_CSS}: missing {needle!r}")

    widget = _read(WIDGET)
    if 'data-bs-popper-config' not in widget or "HEADER_CONTEXT_DROPUP" not in widget:
        errors.append(f"{WIDGET}: footer dropup must wire fixed Popper config")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return 1

    print("FOOTER_TEMPORAL_DOCK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
