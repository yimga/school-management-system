#!/usr/bin/env python3
"""Wave T closeout — smart-links surface gate (batch 1525).

Ensures dead-end / error templates render ``{% render_smart_links %}`` and
the kernel registers parent finance routes on CEZGP pay-all surfaces.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

ERROR_TEMPLATES: dict[str, str | tuple[str, ...]] = {
    "templates/errors/404.html": "error.404",
    "templates/errors/403_control_plane.html": "error.403_control_plane",
    "templates/errors/403.html": ("error.403", "error.403_staff"),
    "templates/errors/500.html": "error.500",
    "templates/errors/503.html": "error.503",
    "templates/errors/offline.html": "error.offline",
    "templates/schools/frozen_account.html": "frozen.",
    "templates/partials/operator_queue_smart_links_banner.html": "operator_queue_smart_link_state",
    "templates/parent/finance.html": "invoice.overdue",
    "templates/portal/photo_upload_expired.html": "photo.link_expired",
    "templates/portal/photo_upload_disabled.html": "photo.feature_disabled",
}

KERNEL_PARENT_URLS = (
    "portal:parent_finance_pay_all",
    "portal:parent_finance",
)


def main() -> int:
    failures: list[str] = []

    kernel_path = ROOT / "apps/platform_runtime/smart_links_kernel.py"
    if not kernel_path.is_file():
        failures.append("smart_links_kernel.py missing")
    else:
        kernel_text = kernel_path.read_text(encoding="utf-8", errors="replace")
        for url_name in KERNEL_PARENT_URLS:
            if url_name not in kernel_text:
                failures.append(f"kernel missing parent url_name {url_name}")
        if "STATE_ERROR_403_STAFF" not in kernel_text:
            failures.append("kernel missing STATE_ERROR_403_STAFF")
        if "STATE_OFFLINE" not in kernel_text:
            failures.append("kernel missing STATE_OFFLINE")

    tag_path = ROOT / "apps/platform_runtime/templatetags/smart_link_tags.py"
    if not tag_path.is_file():
        failures.append("smart_link_tags.py missing")

    for rel, state_needle in ERROR_TEMPLATES.items():
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing template {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "smart_link_tags" not in text:
            failures.append(f"{rel} must load smart_link_tags")
        if "render_smart_links" not in text:
            failures.append(f"{rel} must call render_smart_links")
        needles = (
            (state_needle,)
            if isinstance(state_needle, str)
            else state_needle
        )
        if needles != ("frozen.",) and not any(n in text for n in needles):
            failures.append(f"{rel} must reference one of {needles!r}")

    portal_base = ROOT / "templates/portal_base.html"
    if portal_base.is_file():
        pb = portal_base.read_text(encoding="utf-8", errors="replace")
        has_next_action = (
            "next_action_strip.html" in pb or "rmc_smart_action_hub.html" in pb
        )
        if not has_next_action:
            failures.append(
                "portal_base must include next_action_strip.html or rmc_smart_action_hub.html"
            )
    else:
        failures.append("portal_base.html missing")

    if failures:
        for item in failures:
            print(f"FAIL: {item}", file=sys.stderr)
        print("SMART_LINKS_SURFACE_FAIL", file=sys.stderr)
        return 1

    print("SMART_LINKS_SURFACE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
