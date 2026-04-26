#!/usr/bin/env python3
"""
1053: Verify admin-gravity audit output includes control-plane replacement candidates (heuristic).

Requires ``docs/generated/admin_gravity_audit.json`` from ``audit_admin_gravity.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "docs" / "generated" / "admin_gravity_audit.json"


def main() -> int:
    if not AUDIT.is_file():
        print(f"verify_control_plane_replacement_candidates: FAIL missing {AUDIT}", file=sys.stderr)
        return 1
    data = json.loads(AUDIT.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        print("verify_control_plane_replacement_candidates: FAIL bad schema_version", file=sys.stderr)
        return 1
    cands = data.get("control_plane_replacement_candidates")
    if not isinstance(cands, list):
        print("verify_control_plane_replacement_candidates: FAIL candidates not a list", file=sys.stderr)
        return 1
    summary = data.get("summary") or {}
    apps = summary.get("high_registration_app_labels_gte_3")
    if not isinstance(apps, list) or (apps and not cands):
        # Either no heavy apps (empty list) or we must have at least an empty candidate list
        pass
    if apps and not cands:
        print(
            "verify_control_plane_replacement_candidates: FAIL summary has apps but no candidates",
            file=sys.stderr,
        )
        return 1
    for row in cands:
        if not isinstance(row, dict) or "app_label" not in row:
            print("verify_control_plane_replacement_candidates: FAIL bad row", file=sys.stderr)
            return 1
    print("verify_control_plane_replacement_candidates: PASS (audit JSON + candidates list OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
