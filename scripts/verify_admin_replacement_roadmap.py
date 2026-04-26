#!/usr/bin/env python3
"""
Verify admin control-plane replacement roadmap artifact is present and non-empty.

Requires ``docs/generated/admin_control_plane_replacement_candidates.json`` from
``audit_admin_gravity.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CAND = REPO / "docs" / "generated" / "admin_control_plane_replacement_candidates.json"


def main() -> int:
    if not CAND.is_file():
        print(
            f"verify_admin_replacement_roadmap: FAIL missing {CAND}",
            file=sys.stderr,
        )
        return 1
    data = json.loads(CAND.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        print("verify_admin_replacement_roadmap: FAIL bad schema_version", file=sys.stderr)
        return 1
    rmap = data.get("control_plane_replacement_roadmap")
    if not isinstance(rmap, list) or not rmap:
        print(
            "verify_admin_replacement_roadmap: FAIL roadmap not a non-empty list",
            file=sys.stderr,
        )
        return 1
    for row in rmap:
        if not isinstance(row, dict):
            print("verify_admin_replacement_roadmap: FAIL bad row", file=sys.stderr)
            return 1
        for k in (
            "id",
            "title",
            "priority_rank",
            "status",
        ):
            if k not in row:
                print(
                    f"verify_admin_replacement_roadmap: FAIL missing {k!r} in {row!r}",
                    file=sys.stderr,
                )
                return 1
    dyn = next(
        (row for row in rmap if row.get("id") == "metadata_dynamic_field_operator"),
        None,
    )
    if dyn is None:
        print(
            "verify_admin_replacement_roadmap: FAIL missing metadata_dynamic_field_operator row",
            file=sys.stderr,
        )
        return 1
    if dyn.get("status") not in ("shipped", "partial"):
        print(
            "verify_admin_replacement_roadmap: FAIL metadata_dynamic_field_operator status",
            file=sys.stderr,
        )
        return 1
    cps = dyn.get("cp_url_names")
    if not isinstance(cps, list) or "siteconfig:metadata_dynamic_fields_operator" not in cps:
        print(
            "verify_admin_replacement_roadmap: FAIL metadata_dynamic_field_operator cp_url_names",
            file=sys.stderr,
        )
        return 1
    print("verify_admin_replacement_roadmap: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
