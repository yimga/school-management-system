#!/usr/bin/env python3
"""
Fast mechanical gate for Marketplace Platform mission artifacts (no Django import —
django.setup can be slow in large repos).

Checks:
- docs/developer/MARKETPLACE_MANIFEST.md exists
- manifest_schema defines normalize_platform_manifest, resolve_tenant_catalog_signals,
  pricing_kind / state_machine lifecycle keys

Full behavior is gated by: manage.py test apps.marketplace.tests

Usage: python scripts/verify_marketplace_platform_mission.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST_PY = REPO / "apps" / "marketplace" / "manifest_schema.py"


def main() -> int:
    doc = REPO / "docs" / "developer" / "MARKETPLACE_MANIFEST.md"
    if not doc.is_file():
        print(f"FAIL: missing {doc.relative_to(REPO)}", file=sys.stderr)
        return 1
    if not MANIFEST_PY.is_file():
        print(f"FAIL: missing {MANIFEST_PY.relative_to(REPO)}", file=sys.stderr)
        return 1
    text = MANIFEST_PY.read_text(encoding="utf-8")
    needles = (
        "def normalize_platform_manifest",
        "def resolve_tenant_catalog_signals",
        "pricing_kind",
        '"available"',
        "update_available",
        "rollback_available",
        "previous_catalog_version",
        "compatibility_signals_for_listing",
        "listing_pipeline_phase",
    )
    for n in needles:
        if n not in text:
            print(f"FAIL: manifest_schema missing expected marker {n!r}", file=sys.stderr)
            return 1

    scope_html = REPO / "templates" / "marketplace" / "tenant_scope_consent.html"
    if not scope_html.is_file():
        print(f"FAIL: missing {scope_html.relative_to(REPO)}", file=sys.stderr)
        return 1
    if "data-rmc-mkt-scope-consent" not in scope_html.read_text(encoding="utf-8"):
        print("FAIL: tenant_scope_consent template missing data-rmc-mkt-scope-consent", file=sys.stderr)
        return 1

    print("verify_marketplace_platform_mission: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
