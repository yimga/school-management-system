#!/usr/bin/env python3
"""
§0.4 Advancement CRM depth — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links tenant advancement views, URL names, models, super-shell routes, tests,
and the pre_deploy / phases verifier hooks.

Usage: python scripts/verify_advancement_crm_doc_discipline.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

_REQUIRED = (
    "Advancement CRM depth",
    "Advancement CRM depth (operator contract",
    "apps/schools/views_advancement.py",
    "apps/accounts/urls.py",
    "advancement_donor_list",
    "advancement_donor_create",
    "advancement_donor_detail",
    "advancement_donor_edit",
    "advancement_gift_delete",
    "AdvancementDonor",
    "AdvancementGift",
    "apps/schools/models.py",
    "0038_advancement_donor_gift.py",
    "0040_advancementgift_campaign_name.py",
    "apps/schools/super_urls.py",
    "advancement_hub",
    "advancement_phase2_placeholder",
    "apps/schools/super_views_wedge.py",
    "super_advancement_hub",
    "super_advancement_phase2_placeholder",
    "apps/schools/tests/test_advancement_tenant_crud.py",
    "apps/schools/tests/test_super_advancement_phase2_uuid_school.py",
    "test_wedge_world_class_implemented.py",
    "super:advancement_hub",
    "log_view_exception",
    "scripts/pre_deploy_gate.sh",
    "scripts/verify_phases_3_11_gates.py",
    "verify_advancement_crm_doc_discipline.py",
)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify NORTH_STAR advancement CRM doc anchors (§0.4)."
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
        print(f"verify_advancement_crm_doc_discipline: {exc}", file=sys.stderr)
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
                f"{north_star.relative_to(root)} missing required advancement CRM anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_advancement_crm_doc_discipline: PASS "
        f"({north_star.relative_to(root)} advancement CRM contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_advancement_crm_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
