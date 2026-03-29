#!/usr/bin/env python3
"""
§0.4 UK / international packs — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links regional policy packs, N22 RTL notes, marketing regional JSON, and i18n gates.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = ROOT / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"

_REQUIRED = (
    "UK / international packs",
    "UK / international packs (operator contract",
    "apps/siteconfig/tenant_config.py",
    "REGIONAL_POLICY_PACKS",
    "get_regional_policy_pack",
    "GBR",
    "WEDGES_7_13_GEOGRAPHY_PLAN.md",
    "N22_RTL_AND_REGIONAL_UX.md",
    "apps/siteconfig/context_processors.py",
    "apps/siteconfig/tests/test_n22_region_settings_rtl.py",
    "MARKETING_REGIONAL_JSON.md",
    "verify_i18n_catalog_fresh.py",
    "lint_north_star_i18n.py",
    "verify_phases_3_11_gates.py",
    "sync_i18n_catalog",
    "verify_uk_international_packs_doc_discipline.py",
)


def main() -> int:
    errors: list[str] = []
    if not NORTH_STAR.is_file():
        errors.append(f"Missing {NORTH_STAR.relative_to(ROOT)}")
        return _fail(errors)

    text = NORTH_STAR.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{NORTH_STAR.relative_to(ROOT)} missing required UK/international anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_uk_international_packs_doc_discipline: PASS "
        f"({NORTH_STAR.relative_to(ROOT)} UK/international contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_uk_international_packs_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
