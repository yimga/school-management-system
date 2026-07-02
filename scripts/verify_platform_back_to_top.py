#!/usr/bin/env python3
"""Platform-wide back-to-top wiring gate (batch 1500 + v3.94.3 premium pass)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SHELLS = (
    "templates/portal_base.html",
    "templates/control_plane_skeleton.html",
    "templates/base.html",
    "templates/marketing/base_marketing.html",
    "templates/admin/base.html",
    "templates/admin/base_site.html",
    "templates/partials/rmc_platform_chrome_scripts.html",
)

# control_plane_skeleton.html is deliberately absent: the CI-enforced operator
# tools-tray contract (scripts/verify_operator_tools_tray.py + its tests) FORBIDS
# the always-on policy there — back-to-top still ships via the component include,
# and portal_base's always-policy must stay cockpit-gated per the same contract.
ALWAYS_POLICY_SHELLS = (
    "templates/portal_base.html",
    "templates/base.html",
)

ADMIN_ALWAYS_POLICY_MARKERS = (
    'data-rmc-back-to-top-policy", "always"',
    "data-rmc-back-to-top-policy', 'always'",
)


def main() -> int:
    failures: list[str] = []
    for rel in SHELLS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing shell: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if rel.endswith("rmc_platform_chrome_scripts.html"):
            if "back_to_top.html" not in text:
                failures.append("rmc_platform_chrome_scripts.html: missing back_to_top include")
            continue
        if "back_to_top.html" not in text and "rmc_platform_chrome_scripts.html" not in text:
            failures.append(f"no back-to-top: {rel}")

    for rel in ALWAYS_POLICY_SHELLS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing always-policy shell: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'data-rmc-back-to-top-policy="always"' not in text:
            failures.append(f"missing data-rmc-back-to-top-policy=always: {rel}")

    admin_site = ROOT / "templates/admin/base_site.html"
    if admin_site.is_file():
        site_text = admin_site.read_text(encoding="utf-8", errors="replace")
        if not any(marker in site_text for marker in ADMIN_ALWAYS_POLICY_MARKERS):
            failures.append(
                "admin/base_site.html: manager shell must set data-rmc-back-to-top-policy=always"
            )

    admin_base = ROOT / "templates/admin/base.html"
    if admin_base.is_file():
        admin_text = admin_base.read_text(encoding="utf-8", errors="replace")
        admin_norm = admin_text.replace("\r\n", "\n")
        if (
            "rmc_platform_chrome_scripts.html" not in admin_norm
            or "</div>\n    {% if is_manager_host %}" not in admin_norm
        ):
            failures.append(
                "admin/base.html must mount platform chrome scripts outside .rmc-app-shell"
            )

    fold_css = ROOT / "templates/partials/rmc_platform_chrome_styles.html"
    if fold_css.is_file():
        chrome = fold_css.read_text(encoding="utf-8")
        if "rmc-page-fold-standards.css" not in chrome:
            failures.append("rmc-page-fold-standards.css not in platform chrome styles")
        if "rmc-back-to-top.css" not in chrome:
            failures.append("rmc-back-to-top.css not in platform chrome styles")
    else:
        failures.append("missing rmc_platform_chrome_styles.html")

    js = ROOT / "static/js/_pages/components__back_to_top.js"
    js_text = js.read_text(encoding="utf-8") if js.is_file() else ""
    if not js.is_file() or "data-rmc-mounted" not in js_text:
        failures.append("back-to-top JS missing idempotent mount guard")
    if "RMCBackToTop" not in js_text:
        failures.append("back-to-top JS missing RMCBackToTop export")
    if "alwaysVisiblePolicy" not in js_text:
        failures.append("back-to-top JS missing alwaysVisiblePolicy helper")

    assist = ROOT / "static/js/rmc-assist-dock.js"
    if assist.is_file():
        assist_text = assist.read_text(encoding="utf-8")
        if "rmc-assist-dock__slot--top" in assist_text:
            failures.append("assist dock still buries back-to-top in secondary slot")
        if "data-rmc-back-to-top-floating" not in assist_text:
            failures.append("assist dock missing floating back-to-top contract")
    else:
        failures.append("missing rmc-assist-dock.js")

    template = ROOT / "templates/components/back_to_top.html"
    if template.is_file():
        tpl = template.read_text(encoding="utf-8")
        if "data-rmc-back-to-top-percent" not in tpl:
            failures.append("back-to-top template missing scroll percent chip")
    else:
        failures.append("missing back_to_top.html component")

    if failures:
        print("verify_platform_back_to_top: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"verify_platform_back_to_top: PLATFORM_BACK_TO_TOP_PASS ({len(SHELLS)} shells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
