#!/usr/bin/env python3
"""Mechanical contract: page-aware admin guidance + paired changelist CTAs.

The approved v15/v22 catalog removed the global operator steering strip and
duplicate KPI row from the fold. Guidance is now owned by the page-aware index
intelligence partial and each page's command band.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    findings: list[str] = []

    base = (ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
    if "admin_operator_steering_strip.html" in base:
        findings.append("base.html must not restore the retired global steering strip")
    if "block admin_operator_steering" in base:
        findings.append("base.html must not restore the retired steering-strip block")
    banner = ROOT / "templates/admin/includes/operator_path_banner.html"
    if banner.is_file():
        findings.append("operator_path_banner.html must be deleted (use steering strip)")
    if "admin_operator_outcome_deck.html" in base and "is_manager_host" in base:
        # tenant path may still use outcome deck
        if base.count("admin_operator_outcome_deck.html") > 1 or (
            "is_manager_host" in base
            and "admin_operator_outcome_deck.html" in base.split("is_manager_host")[0]
        ):
            pass
    for legacy in (
        "templates/admin/siteconfig/change_list.html",
        "templates/admin/global_registries/change_list.html",
    ):
        text = (ROOT / legacy).read_text(encoding="utf-8")
        if "rmc-admin-cp-hint" in text:
            findings.append(f"{legacy} must not duplicate cp-hint (use steering strip)")

    header = (ROOT / "templates/admin/includes/admin_changelist_header.html").read_text(
        encoding="utf-8"
    )
    if "RMC_OPERATOR_PAIRED_LINKS" not in header:
        findings.append("admin_changelist_header must render RMC_OPERATOR_PAIRED_LINKS")

    paired_py = (ROOT / "apps/schools/super_admin_paired_surfaces.py").read_text(
        encoding="utf-8"
    )
    if "on_manager_admin" not in paired_py:
        findings.append("super_admin_paired_surfaces must expose paired links on manager admin")

    index = (ROOT / "templates/admin/index_superadmin.html").read_text(encoding="utf-8")
    if "admin/includes/admin_index_intelligence.html" not in index:
        findings.append("index_superadmin must render page-aware index intelligence")
    if "rmc-django-command-band__meta rmc-django-command-band__actions" not in index:
        findings.append("index_superadmin must keep catalog actions in the command band")
    if "rmc-admin-section-jumps" not in index:
        findings.append("index_superadmin must render curated section jumps")
    if "admin_index_kpis" in index:
        findings.append("index_superadmin must not restore the duplicate KPI row")

    app_index = (ROOT / "templates/admin/app_index.html").read_text(encoding="utf-8")
    if "admin_app_index_models" not in app_index or "super_url" not in app_index:
        findings.append("app_index must use admin_app_index_models with super_url")

    if findings:
        for f in findings:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1
    print("verify_admin_steering_strip_contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
