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
)


def main() -> int:
    failures: list[str] = []
    for rel in SHELLS:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing shell: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "back_to_top.html" not in text:
            failures.append(f"no back-to-top: {rel}")

    admin_base = ROOT / "templates/admin/base.html"
    if admin_base.is_file():
        admin_text = admin_base.read_text(encoding="utf-8", errors="replace")
        marker = "</div>\n    {% if is_manager_host %}\n    {% include 'components/back_to_top.html' %}"
        if marker not in admin_text.replace("\r\n", "\n"):
            failures.append(
                "admin/base.html must mount back-to-top outside .rmc-app-shell (fixed positioning)"
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
