#!/usr/bin/env python3
"""
§0.4 UK / international packs — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links regional policy packs, N22 RTL notes, marketing regional JSON, and i18n gates.

Usage: python scripts/verify_uk_international_packs_doc_discipline.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

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


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NORTH_STAR UK/international packs doc anchors (§0.4)."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_uk_international_packs_doc_discipline: {exc}", file=sys.stderr)
        return 1

    north_star = root / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"
    errors: list[str] = []
    if not north_star.is_file():
        errors.append(f"Missing {north_star.relative_to(root)}")
        return _fail(errors)

    text = north_star.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{north_star.relative_to(root)} missing required UK/international anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_uk_international_packs_doc_discipline: PASS "
        f"({north_star.relative_to(root)} UK/international contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_uk_international_packs_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
