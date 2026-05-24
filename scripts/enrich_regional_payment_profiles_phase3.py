#!/usr/bin/env python3
"""Apply SFDP Phase 3 enrichment to regional_payment_profiles.json (batches 1452, 1459–1466)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "apps/finance/data/regional_payment_profiles.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT))
    from apps.finance.payment_local_global_contract import apply_phase3_enrichment, validate_all_profiles

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    enriched: dict = {}
    for iso2, row in sorted(data.items()):
        if not isinstance(row, dict):
            continue
        enriched[iso2] = apply_phase3_enrichment(iso2, row)

    findings = validate_all_profiles(enriched)
    if findings:
        print(f"WARNING: {len(findings)} contract findings (first 10):", file=sys.stderr)
        for item in findings[:10]:
            print(f"  - {item}", file=sys.stderr)

    if args.dry_run:
        print(f"Would write {len(enriched)} enriched profiles")
        return 0

    JSON_PATH.write_text(json.dumps(enriched, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Enriched {len(enriched)} regional payment profiles -> {JSON_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
