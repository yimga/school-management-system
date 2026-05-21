#!/usr/bin/env python3
"""Verifier: tenant School Studio Day-1 Magic contract (batch 1371, pillar P3).

Asserts the structural contract of the 3-act sequence shipped by Agent E3.
Exit code 0 on PASS; 1 on FAIL with a brief findings table.

Checks:
  1. All 4 Day-1 partials exist on disk.
  2. The 4 URL names are wired in ``apps/siteconfig/urls.py``.
  3. ``school_studio_hub`` calls ``Day1MagicService.is_day1_required``.
  4. The Day-1 CSS + JS files exist.
  5. No on-device LLM assumption — no Day-1 source file talks to a direct
     ``ollama`` URL. (AI lives behind ``services.ai_palette``.)
"""

from __future__ import annotations

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def _exists(rel: str) -> bool:
    return (REPO / rel).is_file()


def _text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    findings: list[str] = []

    partials = [
        "templates/siteconfig/partials/tenant_studio_day1_act1_brand.html",
        "templates/siteconfig/partials/tenant_studio_day1_act2_palette.html",
        "templates/siteconfig/partials/tenant_studio_day1_act3_lock.html",
        "templates/siteconfig/partials/tenant_studio_day1_orchestrator.html",
    ]
    for partial in partials:
        if not _exists(partial):
            findings.append(f"missing partial: {partial}")

    urls_text = _text("apps/siteconfig/urls.py")
    expected_url_names = [
        "tenant_studio_day1_act1",
        "tenant_studio_day1_act2",
        "tenant_studio_day1_act3_lock",
        "tenant_studio_day1_reset",
    ]
    for name in expected_url_names:
        if f'name="{name}"' not in urls_text:
            findings.append(f"url name not wired: {name}")

    hub_view_text = _text("apps/siteconfig/views_tenant_studio_hub.py")
    if "Day1MagicService" not in hub_view_text:
        findings.append("hub view does not import Day1MagicService")
    if "is_day1_required" not in hub_view_text:
        findings.append("hub view does not call is_day1_required")

    hub_template = _text("templates/siteconfig/tenant_studio_hub.html")
    if "tenant_studio_day1_orchestrator.html" not in hub_template:
        findings.append("hub template does not conditionally include the day1 orchestrator")
    if "day1_required" not in hub_template:
        findings.append("hub template does not gate on day1_required")

    for static in (
        "static/css/tenant-studio-day1.css",
        "static/js/rmc-tenant-studio-day1.js",
    ):
        if not _exists(static):
            findings.append(f"missing static asset: {static}")

    # No on-device LLM assumption — grep the Day-1-owned files for any direct
    # ollama URL. Day-1 must route through services.ai_palette (which itself
    # sits on services.ai_helpers); a direct ollama endpoint would couple
    # Day-1 to an edge deployment posture.
    ollama_pattern = re.compile(r"ollama[:/]|://[^\s]+:11434", re.IGNORECASE)
    day1_files = [
        "apps/siteconfig/tenant_studio_day1.py",
        "apps/siteconfig/views_tenant_studio_hub.py",
        "static/js/rmc-tenant-studio-day1.js",
        "static/css/tenant-studio-day1.css",
    ] + partials
    for rel in day1_files:
        body = _text(rel)
        if ollama_pattern.search(body):
            findings.append(f"on-device LLM URL detected in {rel}")

    # PaletteVariation contract surface.
    service_text = _text("apps/siteconfig/tenant_studio_day1.py")
    for symbol in (
        "class PaletteVariation",
        "class Day1MagicService",
        "is_day1_required",
        "resolve_brand_seed",
        "generate_variations",
        "lock_palette_choice",
    ):
        if symbol not in service_text:
            findings.append(f"day1 service missing symbol: {symbol}")

    # Logo validator contract surface.
    brand_assets_text = _text("apps/schools/school_brand_assets.py")
    for symbol in (
        "def LogoUploadValidator",
        "def extract_brand_seed_from_logo",
        "tenant-isolation-allow: school-brand-asset-owned-by-school-fk-only",
    ):
        if symbol not in brand_assets_text:
            findings.append(f"school_brand_assets missing: {symbol}")

    print("Day-1 Magic contract verifier")
    print("=" * 36)
    if findings:
        print(f"FAIL — {len(findings)} finding(s):")
        for f in findings:
            print(f"  - {f}")
        return 1
    print("PASS — all Day-1 contract checks succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
