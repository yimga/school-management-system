#!/usr/bin/env python3
"""
§0.4 Advancement CRM depth — documentation discipline (no Django).

Ensures ``docs/NORTH_STAR_TRUST_AND_OPS.md`` keeps the operator contract that
links tenant advancement views, URL names, models, super-shell routes, tests,
and the pre_deploy / phases verifier hooks.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NORTH_STAR = ROOT / "docs" / "NORTH_STAR_TRUST_AND_OPS.md"

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


def main() -> int:
    errors: list[str] = []
    if not NORTH_STAR.is_file():
        errors.append(f"Missing {NORTH_STAR.relative_to(ROOT)}")
        return _fail(errors)

    text = NORTH_STAR.read_text(encoding="utf-8", errors="replace")
    for needle in _REQUIRED:
        if needle not in text:
            errors.append(
                f"{NORTH_STAR.relative_to(ROOT)} missing required advancement CRM anchor: {needle!r}"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_advancement_crm_doc_discipline: PASS "
        f"({NORTH_STAR.relative_to(ROOT)} advancement CRM contract OK)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_advancement_crm_doc_discipline: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
