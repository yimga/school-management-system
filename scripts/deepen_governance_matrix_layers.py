#!/usr/bin/env python3
"""Phase 3D — flip deep_layers flags (MC / MoE / security annex) on matrix rows."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MATRIX_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"

_ARCHETYPE_MOE = frozenset(
    {
        "state_emis_hub",
        "district_trust_overlay",
        "federation_equals",
    }
)


def _framework_ref_for_row(row: dict) -> str | None:
    existing = row.get("statutory_framework_ref")
    if existing:
        return str(existing).strip() or None

    local = row.get("local_terminology")
    if isinstance(local, dict):
        ministry = local.get("ministry_name")
        if isinstance(ministry, dict):
            label = ministry.get("en") or next(
                (v for v in ministry.values() if isinstance(v, str) and v.strip()),
                None,
            )
            if label:
                name = str(row.get("name_en") or row.get("iso_alpha2") or "")
                return f"{label} — {name} statutory reporting (matrix default)."

    name = str(row.get("name_en") or row.get("iso_alpha2") or "")
    return f"{name} education law and privacy compliance (matrix default)." if name else None


def deepen_row(row: dict) -> dict:
    iso = str(row.get("iso_alpha2") or "")
    sovereign = bool(row.get("sovereign_state"))
    tier = str(row.get("research_tier") or "")
    archetype = str(row.get("governance_archetype") or "")

    deep = dict(row.get("deep_layers") or {})
    if tier == "T1" or sovereign:
        deep["mc_profile"] = True
    if sovereign and archetype in _ARCHETYPE_MOE:
        deep["moe_preset"] = True
    elif sovereign and tier in ("T1", "T2"):
        deep["moe_preset"] = True
    if sovereign:
        deep["security_annex"] = True

    row["deep_layers"] = deep
    framework = _framework_ref_for_row(row)
    if framework and not row.get("statutory_framework_ref"):
        row["statutory_framework_ref"] = framework
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Deepen governance matrix deep_layers (Phase 3D)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not MATRIX_PATH.is_file():
        print("FAIL: matrix missing", flush=True)
        return 1

    payload = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    rows = payload.get("rows") or []
    updated = 0
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        new_row = deepen_row(dict(row))
        if new_row != row:
            rows[idx] = new_row
            updated += 1
            iso = str(new_row.get("iso_alpha2") or "")
            if iso and not args.dry_run:
                shard_path = SHARD_DIR / f"{iso}.json"
                if shard_path.is_file():
                    shard_path.write_text(
                        json.dumps(new_row, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )

    payload["rows"] = rows
    payload["deep_layers_pass"] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows_updated": updated,
    }

    if args.dry_run:
        print(f"deepen_governance_matrix_layers: DRY-RUN ({updated} rows would update)")
        return 0

    MATRIX_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"deepen_governance_matrix_layers: OK ({updated} rows updated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
