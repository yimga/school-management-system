#!/usr/bin/env python3
"""Verify country governance matrix coverage and row shape."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
DRIFT_AUDIT_PATH = REPO / "docs" / "generated" / "country_governance_matrix_drift_audit.json"

_DRIFT_COMPARE_FIELDS = (
    "governance_archetype",
    "dissection_status",
    "education_pack_tier",
    "research_tier",
    "statutory_framework_ref",
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

ARCHETYPES = frozenset(
    {
        "single_org_multi_site",
        "district_trust_overlay",
        "federation_equals",
        "state_emis_hub",
    }
)

REQUIRED_FIELDS = (
    "iso_alpha2",
    "governance_archetype",
    "admin_levels",
    "employer_model",
    "reporting_chain",
    "education_pack_tier",
    "continent",
    "official_languages",
    "local_terminology",
    "name_order",
    "research_tier",
)


def _catalog_alpha2() -> set[str]:
    import django

    django.setup()
    from apps.siteconfig.global_catalog import GlobalGeoCatalog

    return {str(c.get("code_alpha2") or "").upper() for c in GlobalGeoCatalog.list_countries() if c.get("code_alpha2")}


def _load_matrix() -> dict[str, Any]:
    if not MATRIX_PATH.is_file():
        raise FileNotFoundError("docs/generated/country_governance_matrix.json missing")
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Country governance matrix verifier")
    parser.add_argument("--allow-skeleton", action="store_true", help="Allow dissection_status=skeleton")
    parser.add_argument("--require-verified", action="store_true", help="Require all rows verified")
    parser.add_argument("--drift-check", action="store_true", help="Check shard parity with aggregate")
    parser.add_argument("--write", action="store_true", help="Write drift audit JSON (with --drift-check)")
    args = parser.parse_args()

    failures: list[str] = []
    drift_findings: list[dict[str, str]] = []
    try:
        matrix = _load_matrix()
    except FileNotFoundError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    catalog = _catalog_alpha2()
    rows = matrix.get("rows") or []
    rows_by_iso = {str(r.get("iso_alpha2") or "").upper(): r for r in rows}
    matrix_codes = set(rows_by_iso)

    if len(rows) != len(catalog):
        failures.append(f"row count {len(rows)} != catalog {len(catalog)}")
    missing = sorted(catalog - matrix_codes)
    extra = sorted(matrix_codes - catalog)
    if missing:
        failures.append(f"missing ISO codes: {', '.join(missing[:10])}" + (f" (+{len(missing)-10})" if len(missing) > 10 else ""))
    if extra:
        failures.append(f"extra ISO codes: {', '.join(extra[:10])}")

    for row in rows:
        iso = str(row.get("iso_alpha2") or "")
        for field in REQUIRED_FIELDS:
            if field not in row:
                failures.append(f"{iso}: missing field {field}")
        archetype = str(row.get("governance_archetype") or "")
        if archetype and archetype not in ARCHETYPES:
            failures.append(f"{iso}: invalid archetype {archetype}")
        status = str(row.get("dissection_status") or "")
        if args.require_verified and status != "verified":
            failures.append(f"{iso}: not verified (status={status})")
        elif not args.allow_skeleton and status == "skeleton":
            failures.append(f"{iso}: skeleton row not allowed without --allow-skeleton")
        sovereign = bool(row.get("sovereign_state"))
        territory = bool(row.get("territory"))
        if territory and sovereign:
            failures.append(f"{iso}: territory and sovereign_state both true")
        if args.require_verified and sovereign and not row.get("admin_levels"):
            failures.append(f"{iso}: sovereign state missing admin_levels")
        shard = SHARD_DIR / f"{iso}.json"
        if not shard.is_file():
            failures.append(f"{iso}: missing shard {shard.relative_to(REPO)}")
        elif args.drift_check:
            shard_row = json.loads(shard.read_text(encoding="utf-8"))
            if shard_row.get("iso_alpha2") != iso:
                failures.append(f"{iso}: shard iso mismatch")
            aggregate_row = rows_by_iso.get(iso) or {}
            for field in _DRIFT_COMPARE_FIELDS:
                shard_val = shard_row.get(field)
                agg_val = aggregate_row.get(field)
                if shard_val != agg_val:
                    msg = f"{iso}: shard/aggregate drift on {field}"
                    failures.append(msg)
                    drift_findings.append(
                        {
                            "iso_alpha2": iso,
                            "field": field,
                            "shard": str(shard_val),
                            "aggregate": str(agg_val),
                        }
                    )

    if args.drift_check and args.write:
        from datetime import datetime, timezone

        DRIFT_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRIFT_AUDIT_PATH.write_text(
            json.dumps(
                {
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "verdict": "PASS" if not drift_findings else "FAIL",
                    "finding_count": len(drift_findings),
                    "findings": drift_findings,
                    "row_count": len(rows),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    if failures:
        print("verify_country_governance_matrix: FAIL", file=sys.stderr)
        for line in failures[:25]:
            print(f"  - {line}", file=sys.stderr)
        if len(failures) > 25:
            print(f"  - ... {len(failures) - 25} more", file=sys.stderr)
        return 1

    print(f"verify_country_governance_matrix: PASS ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
