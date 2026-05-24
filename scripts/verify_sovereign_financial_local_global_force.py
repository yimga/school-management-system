#!/usr/bin/env python3
"""Plan gate for SFDP Phase 3 local-global financial force."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PLAN = ROOT / "docs/plans/SOVEREIGN_FINANCIAL_DELIVERY_PLATFORM_PLAN.md"
PROFILES = ROOT / "apps/finance/data/regional_payment_profiles.json"

REQUIRED_PLAN_TOKENS = (
    "SOVEREIGN_FINANCIAL_LOCAL_GLOBAL_FORCE",
    "country-native in 200+ countries",
    "local currency",
    "local payment vocabulary",
    "offline/cash fallback posture",
    "one global financial platform",
    "One server-authoritative ledger",
    "One PSP adapter registry",
    "One webhook normalizer envelope",
    "Playwright",
    "390px",
    "768px",
    "1366px",
)

ANCHOR_COUNTRIES = (
    "NG",
    "GH",
    "CM",
    "KE",
    "BR",
    "IN",
    "ID",
    "AE",
    "FR",
    "CA",
)


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from apps.finance.payment_local_global_contract import (
        PHASE3_REQUIRED_FIELDS,
        apply_phase3_enrichment,
        validate_profile_contract,
    )

    findings: list[str] = []

    if not PLAN.is_file():
        findings.append(f"missing {PLAN.relative_to(ROOT)}")
        plan_text = ""
    else:
        plan_text = PLAN.read_text(encoding="utf-8", errors="replace")

    for token in REQUIRED_PLAN_TOKENS:
        if token not in plan_text:
            findings.append(f"plan missing local-global token: {token}")

    for batch in range(1451, 1476):
        if f"**{batch}**" not in plan_text:
            findings.append(f"plan missing Phase 3 batch {batch}")

    if not PROFILES.is_file():
        findings.append(f"missing {PROFILES.relative_to(ROOT)}")
        profiles: dict[str, dict] = {}
    else:
        profiles = json.loads(PROFILES.read_text(encoding="utf-8"))

    if len(profiles) < 200:
        findings.append(f"regional payment profiles has {len(profiles)} countries; need >=200")

    missing_anchor = [iso2 for iso2 in ANCHOR_COUNTRIES if iso2 not in profiles]
    if missing_anchor:
        findings.append(f"missing anchor country profiles: {', '.join(missing_anchor)}")

    for iso2, row in sorted(profiles.items()):
        enriched = apply_phase3_enrichment(iso2, row if isinstance(row, dict) else {})
        findings.extend(validate_profile_contract(enriched, iso2=iso2))

    for rel in (
        "apps/finance/payment_local_global_contract.py",
        "apps/finance/payment_rail_taxonomy.py",
        "scripts/enrich_regional_payment_profiles_phase3.py",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    if findings:
        print("verify_sovereign_financial_local_global_force: FAIL", file=sys.stderr)
        for item in findings[:20]:
            print(f"  - {item}", file=sys.stderr)
        if len(findings) > 20:
            print(f"  ... and {len(findings) - 20} more", file=sys.stderr)
        return 1

    print(
        "verify_sovereign_financial_local_global_force: "
        "SOVEREIGN_FINANCIAL_LOCAL_GLOBAL_FORCE_PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
