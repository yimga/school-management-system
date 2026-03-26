#!/usr/bin/env python3
"""
Program Phase 10 (ecosystem: marketplace / packs / migration / interop) +
Program Phase 11 (marketing narrative homepage) — static acceptance gate.

No database. Verifies template/CSS/engine markers that encode the shipped product
contract (aligned with SOT 3.2.3 marketplace slice + 3.2.4 marketing front).

Run: python scripts/verify_program_phase10_phase11_gates.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Relative path -> required substrings (all must be present).
PHASE10_STATIC_MARKERS: dict[str, tuple[str, ...]] = {
    "templates/marketplace/tenant_app_catalog.html": (
        "data-phase9-ecosystem-hub",
        "data-phase9-listing-trust",
        "data-listing-compatibility",
        "Migration & interoperability hub",
        "Rollback expectations",
        "Install to sandbox",
        "catalog-placeholder.svg",
    ),
    "templates/marketplace/app_catalog.html": (
        "data-phase9-listing-trust",
        "data-listing-compatibility",
        "Install with trust, not guesswork.",
    ),
    "templates/accounts/migration_wizard.html": (
        "data-decision-engine",
        "data-migration-source-detection",
        "data-migration-confidence",
        "Staged rollout & safety",
        "Migration run history",
    ),
    "templates/accounts/district_lms_interop.html": (
        "data-phase9-interop-workbench",
        "data-phase9-connector-health",
    ),
    "templates/siteconfig/installed_packages_rollback.html": (
        "data-phase9-pack-staged-rollout",
        "Staged rollout",
    ),
}

PHASE11_STATIC_MARKERS: dict[str, tuple[str, ...]] = {
    "templates/schools/marketing_landing.html": (
        "data-phase10-marketing-narrative",
        "mkt-narrative-phase10",
        'id="hero"',
        'id="platform-pillars"',
        'id="one-platform"',
        'id="launch-in-minutes"',
        'id="product-visualization"',
        'id="ecosystem"',
        'id="migration"',
        'id="for-your-role"',
        'id="security-compliance"',
        'id="final-cta"',
        "mkt-studio-pinned",
        "live_flow_preview.html",
        "marketing-narrative-phase10.css",
        "data-phase10-role-visuals",
    ),
    "templates/marketing/partials/live_flow_preview.html": (
        'id="live-flow-preview"',
        "data-mkt-live-flow",
    ),
    "static/marketing/css/marketing-narrative-phase10.css": (
        ".marketing-home.mkt-narrative-phase10",
        ".mkt-studio-pinned",
    ),
}

# Engine: pack lifecycle primitives (versioned units / staged apply).
PACK_ENGINE_MARKERS: tuple[str, ...] = (
    "apply_stage",
    "PackageEngine",
    "rollback",
)


def _read(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        raise FileNotFoundError(rel)
    return path.read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []

    for rel, markers in PHASE10_STATIC_MARKERS.items():
        text = _read(rel)
        missing = [m for m in markers if m not in text]
        if missing:
            failures.append(f"Phase10 {rel}: missing {missing}")

    for rel, markers in PHASE11_STATIC_MARKERS.items():
        text = _read(rel)
        missing = [m for m in markers if m not in text]
        if missing:
            failures.append(f"Phase11 {rel}: missing {missing}")

    engine_text = _read("apps/packages/engine.py")
    eng_missing = [m for m in PACK_ENGINE_MARKERS if m not in engine_text]
    if eng_missing:
        failures.append(f"Phase10 apps/packages/engine.py: missing {eng_missing}")

    if failures:
        print("FAIL program Phase10/Phase11 static gates:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("OK   program Phase10 (ecosystem) + Phase11 (marketing narrative) static gates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
