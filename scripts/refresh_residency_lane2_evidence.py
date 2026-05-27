#!/usr/bin/env python3
"""Refresh Lane 2 residency evidence JSON from in-repo scaffold proofs (honest; no live region)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_DIR = ROOT / "var/evidence/geos-99/compliance"


def _run(script: str) -> bool:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    onboarding_ok = _run("verify_data_residency_onboarding.py")
    router_ok = _run("verify_multi_region_router_scaffold.py")
    honesty_ok = _run("verify_glocal_out_of_scope_honesty.py")

    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "pillar": "geos-99-compliance-residency",
        "lane": 2,
        "status": "operator_checklist_scaffold",
        "second_physical_region_live": False,
        "enable_multi_region": False,
        "checklist": {
            "postgres_second_cluster_provisioned": False,
            "databases_alias_registered": False,
            "pilot_tenant_regional_cluster_mapped": False,
            "verify_data_residency_strict_passed": False,
            "backup_drill_logged": False,
            "enable_multi_region_flipped": False,
        },
        "in_repo_proof": {
            "data_residency_onboarding_pass": onboarding_ok,
            "multi_region_router_scaffold_pass": router_ok,
            "glocal_out_of_scope_honesty_pass": honesty_ok,
            "dynamic_db_routing_module": "apps/platform_runtime/dynamic_db_routing.py",
            "middleware": "apps.platform_runtime.middleware_regional_db.RegionalDatabaseMiddleware",
        },
        "operator_note": (
            "Refreshed by refresh_residency_lane2_evidence.py. "
            "Set second_physical_region_live=true only after operator provisions a second cluster."
        ),
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = EVIDENCE_DIR / f"residency_{stamp}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    latest = EVIDENCE_DIR / "residency_latest.json"
    latest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not (onboarding_ok and router_ok and honesty_ok):
        print("refresh_residency_lane2_evidence: FAIL (scaffold verifiers)", file=sys.stderr)
        return 1

    print(f"refresh_residency_lane2_evidence: OK wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
