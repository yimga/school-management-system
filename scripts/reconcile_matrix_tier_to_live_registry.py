#!/usr/bin/env python3
"""Reconcile matrix `education_pack_tier` against the live country registry.

Walks every shard, asks `_expected_tier(iso)` (the same source of truth the
country_layer_consistency verifier uses), and rewrites the shard tier when it
drifts. Mirrors the change into the master matrix file. Idempotent.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOGGER = logging.getLogger("reconcile_matrix_tier")

REPO = Path(__file__).resolve().parents[1]
SHARD_DIR = REPO / "docs" / "generated" / "country_governance_matrix"
MASTER_PATH = REPO / "docs" / "generated" / "country_governance_matrix.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _expected_tier(alpha2: str) -> str:
    import django

    django.setup()
    from apps.siteconfig import _seed_country_localization as seed
    from apps.siteconfig.country_localization_service import resolve_country_pack

    if alpha2 in seed.COUNTRY_LOCALIZATION:
        return "tier1_native"
    pack = resolve_country_pack(alpha2)
    source = str(pack.get("_pack_source") or pack.get("pack_source") or "")
    if "regional" in source:
        return "tier1_regional_clone"
    return "generic_fallback"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not SHARD_DIR.is_dir():
        LOGGER.error("missing shard dir: %s", SHARD_DIR.relative_to(REPO))
        return 1

    changes: list[tuple[str, str, str]] = []
    for shard_path in sorted(SHARD_DIR.glob("*.json")):
        row = json.loads(shard_path.read_text(encoding="utf-8"))
        iso = str(row.get("iso_alpha2") or shard_path.stem)
        current = str(row.get("education_pack_tier") or "")
        expected = _expected_tier(iso)
        if current != expected:
            row["education_pack_tier"] = expected
            shard_path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
            changes.append((iso, current, expected))

    if MASTER_PATH.is_file() and changes:
        master = json.loads(MASTER_PATH.read_text(encoding="utf-8"))
        rows = master.get("rows") or master.get("items") or master.get("countries") or []
        if isinstance(rows, list):
            iso_to_expected = {iso: exp for iso, _, exp in changes}
            for row in rows:
                if isinstance(row, dict):
                    iso = str(row.get("iso_alpha2") or "")
                    if iso in iso_to_expected:
                        row["education_pack_tier"] = iso_to_expected[iso]
            master["regenerated_at"] = datetime.now(timezone.utc).isoformat()
            MASTER_PATH.write_text(json.dumps(master, indent=2) + "\n", encoding="utf-8")

    if changes:
        LOGGER.info("reconciled %d shards:", len(changes))
        for iso, old, new in changes[:60]:
            LOGGER.info("  %s: %s -> %s", iso, old, new)
        if len(changes) > 60:
            LOGGER.info("  ... and %d more", len(changes) - 60)
    else:
        LOGGER.info("no drift: %d shards already aligned", len(list(SHARD_DIR.glob("*.json"))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
