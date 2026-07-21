#!/usr/bin/env python3
"""MAX Wave 4: chrome band-count / fold SLA for operator + tenant admin hubs.

Fails when a hub template stacks too many pre-work chrome bands before
``data-rmc-work-root``, or includes Option-A / readiness meta strips without
the suppress contract.

Usage:
  python scripts/verify_band_count_fold_sla.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Chrome include tokens that each count as one band when present.
BAND_TOKENS = (
    "rmc_operational_center_frame.html",
    "rmc_page_masthead.html",
    "next_action_strip.html",
    "tenant_option_a_strip.html",
    "tenant_blueprint_option_a_strip.html",
    "platform_readiness_strip.html",
    "luxury_major_audit_contract.html",
    "rmc_page_explain",
)

# Surfaces that must open with work (masthead + ≤1 optional band, then work-root).
HUB_GLOBS = (
    "templates/schools/super_*.html",
    "templates/schools/billing_dashboard.html",
    "templates/finance/dashboard.html",
    "templates/platform_runtime/school_configuration_center.html",
    "templates/platform_runtime/configuration_center.html",
    "templates/platform_runtime/blueprint_marketplace.html",
    "templates/platform_runtime/pack_marketplace.html",
    "templates/platform_runtime/change_requests.html",
    "templates/marketplace/tenant_app_catalog.html",
    "templates/accounts/backend_dashboard.html",
    "templates/siteconfig/feature_control_panel.html",
)

MAX_BANDS_BEFORE_WORK = 2
OPTION_A_FORBIDDEN = (
    "tenant_option_a_strip.html",
    "tenant_blueprint_option_a_strip.html",
)


def _hub_paths() -> list[Path]:
    out: list[Path] = []
    for pattern in HUB_GLOBS:
        out.extend(ROOT.glob(pattern))
    # Dedupe
    return sorted({p.resolve() for p in out if p.is_file()})


def _count_bands(text: str) -> int:
    """Count distinct chrome band kinds (if/else duplicate includes count once)."""
    present = {token for token in BAND_TOKENS if token in text}
    # Frame embeds masthead — do not double-count an explicit masthead include
    # on the same page when the frame is also present.
    if "rmc_operational_center_frame.html" in present and "rmc_page_masthead.html" in present:
        present.discard("rmc_page_masthead.html")
    return len(present)


def main() -> int:
    failed: list[str] = []
    checked = 0
    for path in _hub_paths():
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Skip pure partial shells / redirects with almost no chrome.
        if "extends" not in text and "include" not in text:
            continue
        checked += 1
        suppress = "rmc-max-suppress-meta-option-a" in text
        for banned in OPTION_A_FORBIDDEN:
            if banned in text and not suppress:
                failed.append(f"{rel}: Option-A strip `{banned}` without suppress — purge or add rmc-max-suppress-meta-option-a")
        bands = _count_bands(text)
        has_work = "data-rmc-work-root" in text or "rmc_operational_center_frame.html" in text
        # Frame emits work-root; pages that include frame are covered.
        if "rmc_operational_center_frame.html" not in text and "data-rmc-work-root" not in text:
            # Mission / money / setup twins must declare work-root explicitly.
            if any(
                x in rel
                for x in (
                    "backend_dashboard",
                    "billing_dashboard",
                    "finance/dashboard",
                    "school_configuration",
                    "super_dashboard",
                    "feature_control",
                )
            ):
                failed.append(f"{rel}: missing data-rmc-work-root (fold SLA)")
        if has_work and bands > MAX_BANDS_BEFORE_WORK and not suppress:
            # Allow suppress class to mark intentional dense landings under review.
            if "rmc-max-band-allow" not in text:
                failed.append(
                    f"{rel}: {bands} chrome bands before work (max {MAX_BANDS_BEFORE_WORK})"
                )
    if failed:
        print("FAIL band-count / fold SLA:", file=sys.stderr)
        for f in failed:
            print(f"  {f}", file=sys.stderr)
        print(f"checked={checked} failed={len(failed)}", file=sys.stderr)
        return 1
    print(f"OK: band-count / fold SLA ({checked} hubs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
