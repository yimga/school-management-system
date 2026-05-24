#!/usr/bin/env python3
"""
Expand regional_payment_profiles.json with stub corridor rows (SFDP 1441–1442).

Does NOT hand-author 200 countries — adds only explicit ISO2 codes passed via --add.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "apps/finance/data/regional_payment_profiles.json"

# Phase 2 expansion tranche (same shape as 1423 — operator fills live PSP later)
PHASE2_STUB_ISO2 = ("ET", "ML", "BF", "BJ", "TG", "NE", "MW", "ZM", "AO", "EG")


def _stub_row(iso2: str) -> dict:
    return {
        "country_code": iso2,
        "label": iso2,
        "currency": "USD",
        "primary_rail": "BANK",
        "backup_rail": "CASH",
        "primary_rails": ["BANK", "CARD"],
        "backup_rails": ["CASH"],
        "manual_fallback": True,
        "manual_receipt_allowed": True,
        "offline_receipt_allowed": True,
        "reconciliation_required": True,
        "reconciliation": "staff_matches_offline_intent_to_bank_statement",
        "notes": f"SFDP Phase 2 stub — replace with corridor-specific rails before verified_live.",
        "provider_notes": "Registry stub only; connect PSP per payment_lane2_checklist.py.",
        "provider_setup_status": "external_required",
        "operator_ready_label": "Stub corridor — configure primary PSP when product commits.",
        "operator_setup_steps": [
            f"Set compliance profile country to {iso2}.",
            "Add payments Integration for chosen PSP.",
            "Run check_payment_gateways after live keys land.",
            "File evidence under var/evidence/geos-99/psp/ before verified_live.",
        ],
        "tenant_setup_steps": [
            f"Confirm school country {iso2} on compliance profile.",
            "Enable offline receipt path if MoMo/card not yet live.",
        ],
    }


def _all_iso2_from_pycountry() -> list[str]:
    import pycountry

    codes: list[str] = []
    for country in pycountry.countries:
        alpha2 = getattr(country, "alpha_2", None)
        if alpha2 and len(alpha2) == 2:
            codes.append(alpha2.upper())
    return sorted(set(codes))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--add",
        nargs="*",
        default=None,
        help="ISO2 codes to ensure exist (default Phase 2 tranche when neither --add nor --all-iso2)",
    )
    parser.add_argument(
        "--all-iso2",
        action="store_true",
        help="Add stub rows for every ISO 3166-1 alpha-2 code from pycountry (~200+)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.all_iso2:
        to_add = _all_iso2_from_pycountry()
    elif args.add is not None:
        to_add = [str(x).strip().upper() for x in args.add]
    else:
        to_add = list(PHASE2_STUB_ISO2)

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    added: list[str] = []
    for raw in to_add:
        iso2 = str(raw).strip().upper()[:2]
        if len(iso2) != 2:
            continue
        if iso2 not in data:
            data[iso2] = _stub_row(iso2)
            added.append(iso2)

    if args.dry_run:
        print(f"Would add: {', '.join(added) or '(none)'}")
        return 0

    if added:
        JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Added {len(added)} stub corridors (total keys: {len(data)})")
    else:
        print(f"No new ISO2 rows needed (total keys: {len(data)})")
    if args.all_iso2 and len(data) < 200:
        print(f"WARNING: expected >=200 ISO2 rows, got {len(data)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
