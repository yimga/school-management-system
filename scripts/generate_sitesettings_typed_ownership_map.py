#!/usr/bin/env python3
"""
Build ``docs/generated/sitesettings_typed_ownership_map.json`` from ``domain_ownership``.

Categories (1042):
- ``slim_physical_row`` — keys that remain on the slim ``SiteSettings`` ORM row (Phase B).
- ``runtime_payload`` — virtual keys resolved via ``get_effective_site_settings`` / payload.
- ``typed_migration_target`` — fields slated to move to first-class bounded-context tables.
- ``deprecated`` — ownership domain ``delete`` or legacy-only.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "generated" / "sitesettings_typed_ownership_map.json"


def _load_domain_ownership():
    import importlib.util

    p = REPO / "apps" / "siteconfig" / "domain_ownership.py"
    spec = importlib.util.spec_from_file_location("domain_ownership_mapgen", p)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load domain_ownership")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.EXACT_FIELD_OWNERS, mod.PREFIX_FIELD_OWNERS


def _classify(field: str, owner: str) -> str:
    if owner == "delete":
        return "deprecated"
    if field in ("maintenance_mode", "updated_at"):
        return "slim_physical_row"
    if owner == "marketplace_integrations":
        return "typed_migration_target"
    if owner == "brand_experience":
        return "typed_migration_target"
    if owner in ("reports", "documents", "runtime_blueprints", "policies_rules"):
        return "runtime_payload"
    return "runtime_payload"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stdout-json",
        action="store_true",
    )
    args = parser.parse_args(argv)
    exact, _prefixes = _load_domain_ownership()
    fields: dict[str, dict[str, str]] = {}
    for k, dom in sorted(exact.items()):
        fields[k] = {
            "ownership_domain": dom,
            "phase_b_category": _classify(k, dom),
        }
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_module": "apps/siteconfig/domain_ownership.py",
        "field_count": len(fields),
        "fields": fields,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.stdout_json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"generate_sitesettings_typed_ownership_map: OK -> {OUT.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
