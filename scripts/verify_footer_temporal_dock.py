#!/usr/bin/env python3
"""Footer temporal dock -- centered clock/weather chip on every dashboard footer.

The dock's stylesheet is required on the shells that RENDER the dock, and the
set of those shells is derived, not hand-listed. The hand-list previously named
templates/admin/base_site.html, which reaches no footer partial at all: the
/admin/ model workbench deliberately delegates its footer to the control plane
(templates/admin/base.html carries the rationale, and
apps/siteconfig/tests/test_footer_surface_contract.py asserts it does NOT wire
the civic footer). Demanding the dock stylesheet there demanded dead CSS, and
the gate failed for it every run.

Delivery is resolved through scripts/shell_css_contract.py, so a stylesheet that
arrives inside a manifest-declared bundle counts -- but only when the bundle is
linked by that shell, lists the stylesheet as a source, and that source's sha256
still matches the file on disk.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import shell_css_contract  # noqa: E402

#: Every shell that could plausibly mount a footer. Which of them MUST carry the
#: dock CSS is decided below by asking whether it actually renders the partial.
CANDIDATE_SHELLS = (
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

    dock_name = DOCK_PARTIAL.split("/")[-1]
    rendering = [rel for rel in CANDIDATE_SHELLS if shell_css_contract.renders(rel, dock_name)]
    if not rendering:
        # Without this the gate would quietly pass the day the dock is retired,
        # while still asserting five CSS needles about a component nobody renders.
        errors.append(
            f"no shell renders {dock_name} -- the dock is unwired; retire this gate "
            f"or restore the include"
        )
    for rel in rendering:
        finding = shell_css_contract.missing_stylesheet(rel, "rmc-footer-temporal-dock.css")
        if finding:
            errors.append(finding)

    for rel in FOOTER_PARTIALS:
        if dock_name not in shell_css_contract.reachable_text(rel):
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
    print(f"  shells rendering the dock: {len(rendering)}")
    for rel in rendering:
        status, detail = shell_css_contract.resolve(rel, "rmc-footer-temporal-dock.css")
        print(f"    {rel}  [{status}] {detail}")
    for rel in CANDIDATE_SHELLS:
        if rel not in rendering:
            print(f"    {rel}  [n/a] renders no footer dock, so the CSS is not required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
