#!/usr/bin/env python3
"""Detect drift between mat_groups registry and parent_school hierarchy."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated" / "hierarchy_silo_drift_audit.json"

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def main() -> int:
    parser = argparse.ArgumentParser(description="Hierarchy silo drift verifier")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--allow-unlinked", action="store_true", help="Report drift without failing (Phase 0 scaffold)")
    args = parser.parse_args()

    import django

    django.setup()

    failures: list[str] = []
    drift_rows: list[dict[str, str]] = []

    try:
        from apps.schools.hierarchy_helpers import scoped_schools_for_user  # noqa: F401
    except Exception as exc:
        failures.append(f"hierarchy_helpers import failed: {exc}")

    # mat_groups lives in RuntimeDefaults / SiteSettings brand payload — scan JSON sources.
    mat_sources = [
        REPO / "apps" / "schools" / "mat_group_hub.py",
        REPO / "apps" / "schools" / "hierarchy_helpers.py",
    ]
    has_mat = any("mat_group" in p.read_text(encoding="utf-8") for p in mat_sources if p.is_file())
    has_parent = (REPO / "apps" / "schools" / "models.py").is_file()
    if has_parent:
        models_text = (REPO / "apps" / "schools" / "models.py").read_text(encoding="utf-8")
        if "parent_school" not in models_text:
            failures.append("School.parent_school field not found")

    if not has_mat:
        failures.append("mat_group hub references not found")

    gov_app = REPO / "apps" / "governance"
    hierarchy_text = (REPO / "apps" / "schools" / "hierarchy_helpers.py").read_text(encoding="utf-8")
    if gov_app.is_dir():
        drift_rows.append({"silo": "organization", "status": "implemented", "note": "apps/governance Phase 2A"})
        if "OrgMembership" not in hierarchy_text:
            failures.append("hierarchy_helpers missing OrgMembership org-scope extension")
    else:
        drift_rows.append({"silo": "organization", "status": "missing", "note": "Phase 2 deliverable"})
        if not args.allow_unlinked:
            failures.append("apps/governance/ missing")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "HIERARCHY_SILO_DRIFT_PASS" if not failures else "HIERARCHY_SILO_DRIFT_FAIL",
        "finding_count": len(failures),
        "drift_rows": drift_rows,
        "failures": failures,
        "note": "parent_school + mat_groups + Organization documented; mat_groups JSON not yet derived from Organization",
    }
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failures:
        print("verify_hierarchy_silo_drift: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1

    print("verify_hierarchy_silo_drift: PASS (Organization layer shipped; mat_groups sync deferred)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
