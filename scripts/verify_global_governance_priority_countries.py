#!/usr/bin/env python3
"""Verify priority-country governance dissection (CM, NG, US, GB, IN)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MATRIX = ROOT / "docs/generated/country_governance_matrix.json"
LEDGER = ROOT / "docs/generated/country_dissection_ledger.json"
PRIORITY = ("CM", "NG", "US", "GB", "IN")
DEEP_LAYER_KEYS = ("mc_profile", "moe_preset", "security_annex", "subdivisions_seeded")


def main() -> int:
    failures: list[str] = []
    if not MATRIX.is_file():
        print("GLOBAL_GOVERNANCE_PRIORITY_COUNTRIES_FAIL: matrix missing", file=sys.stderr)
        return 1

    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = {str(r.get("iso_alpha2")): r for r in matrix.get("rows") or []}

    ledger_by_iso: dict[str, dict] = {}
    if LEDGER.is_file():
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        ledger_by_iso = {
            str(e.get("iso_alpha2")): e for e in ledger.get("entries") or []
        }

    for iso in PRIORITY:
        row = rows.get(iso)
        if not row:
            failures.append(f"{iso}: missing matrix row")
            continue
        if row.get("dissection_status") != "verified":
            failures.append(f"{iso}: dissection_status={row.get('dissection_status')}")
        if not row.get("admin_levels"):
            failures.append(f"{iso}: missing admin_levels")
        if not row.get("governance_archetype"):
            failures.append(f"{iso}: missing governance_archetype")
        deep = row.get("deep_layers") or {}
        for key in DEEP_LAYER_KEYS:
            if not deep.get(key):
                failures.append(f"{iso}: deep_layers.{key} not true")
        entry = ledger_by_iso.get(iso)
        if entry and entry.get("dissection_status") != row.get("dissection_status"):
            failures.append(f"{iso}: ledger/matrix status mismatch")

    if failures:
        print("GLOBAL_GOVERNANCE_PRIORITY_COUNTRIES_FAIL", file=sys.stderr)
        for msg in failures:
            print(f"  {msg}", file=sys.stderr)
        return 1

    print(f"GLOBAL_GOVERNANCE_PRIORITY_COUNTRIES_PASS cohort={','.join(PRIORITY)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
