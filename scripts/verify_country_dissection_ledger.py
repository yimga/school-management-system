#!/usr/bin/env python3
"""Verify country dissection ledger tracks all ISO codes and wave progress."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO / "docs" / "generated" / "country_dissection_ledger.json"
MATRIX_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

ALLOWED_STATUS = frozenset({"pending", "skeleton", "languages", "governance", "verified"})


def _catalog_alpha2() -> set[str]:
    import django

    django.setup()
    from apps.siteconfig.global_catalog import GlobalGeoCatalog

    return {str(c.get("code_alpha2") or "").upper() for c in GlobalGeoCatalog.list_countries() if c.get("code_alpha2")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Country dissection ledger verifier")
    parser.add_argument("--allow-skeleton", action="store_true", help="Allow skeleton status")
    parser.add_argument("--require-verified", action="store_true", help="Require 249/249 verified")
    args = parser.parse_args()

    failures: list[str] = []
    if not LEDGER_PATH.is_file():
        print("FAIL: country_dissection_ledger.json missing", file=sys.stderr)
        return 1

    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    entries = ledger.get("entries") or []
    catalog = _catalog_alpha2()
    ledger_codes = {str(e.get("iso_alpha2") or "").upper() for e in entries}

    if len(entries) != len(catalog):
        failures.append(f"ledger count {len(entries)} != catalog {len(catalog)}")
    missing = sorted(catalog - ledger_codes)
    if missing:
        failures.append(f"missing ledger entries: {len(missing)}")

    verified = sum(1 for e in entries if e.get("dissection_status") == "verified")
    if args.require_verified and verified != len(catalog):
        failures.append(f"verified {verified}/{len(catalog)} — require all verified")

    for entry in entries:
        iso = str(entry.get("iso_alpha2") or "")
        status = str(entry.get("dissection_status") or "")
        if status not in ALLOWED_STATUS:
            failures.append(f"{iso}: invalid dissection_status {status}")
        if not args.allow_skeleton and status == "skeleton":
            failures.append(f"{iso}: skeleton not allowed without --allow-skeleton")

    if MATRIX_PATH.is_file():
        matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
        matrix_by_iso = {str(r.get("iso_alpha2")): r for r in matrix.get("rows") or []}
        for entry in entries:
            iso = str(entry.get("iso_alpha2") or "")
            row = matrix_by_iso.get(iso)
            if not row:
                failures.append(f"{iso}: missing matrix row")
                continue
            if entry.get("dissection_status") != row.get("dissection_status"):
                failures.append(f"{iso}: ledger/matrix status mismatch")

    if failures:
        print("verify_country_dissection_ledger: FAIL", file=sys.stderr)
        for line in failures[:20]:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print(f"verify_country_dissection_ledger: PASS ({len(entries)} entries, verified={verified})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
