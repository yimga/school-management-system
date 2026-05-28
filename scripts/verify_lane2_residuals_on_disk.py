#!/usr/bin/env python3
"""Verify Lane 2 residual evidence files exist on disk (batches 1170, 1199, 1175)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "var" / "evidence" / "geos-99"
ROLLUP = ROOT / "docs" / "generated" / "geos_lane2_residual_evidence.json"


def _latest(glob_pattern: str) -> Path | None:
    matches = sorted(EVIDENCE.glob(glob_pattern))
    return matches[-1] if matches else None


def main() -> int:
    findings: list[str] = []

    stripe = _latest("psp/stripe/lane2_batch1170_preflight_*.json")
    if not stripe:
        findings.append("missing var/evidence/geos-99/psp/stripe/lane2_batch1170_preflight_*.json")
    else:
        data = json.loads(stripe.read_text(encoding="utf-8"))
        status = str(data.get("evidence_status") or "")
        if status not in {"verified_live", "repo_complete", "repo_verified"}:
            findings.append(f"1170 preflight bad evidence_status: {status!r}")
        if data.get("phase1_charge_status") != "pending_operator":
            findings.append("1170 phase1 must stay pending_operator until supervised charge")
        phase1 = ROOT / "var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.json"
        if not phase1.is_file():
            findings.append("missing phase1_platform_charge_evidence.json (init-evidence)")

    render = _latest("render/sha_parity_*.json")
    if not render:
        findings.append("missing var/evidence/geos-99/render/sha_parity_*.json")
    else:
        data = json.loads(render.read_text(encoding="utf-8"))
        if not data.get("local_head_sha"):
            findings.append("render sha_parity missing local_head_sha")

    pilot = _latest("pilot/gilead-school/intake_ready_*.json")
    backlog = EVIDENCE / "pilot" / "gilead-school" / "defect_backlog.json"
    if not pilot:
        findings.append("missing pilot/gilead-school/intake_ready_*.json")
    if not backlog.is_file():
        findings.append("missing pilot/gilead-school/defect_backlog.json")

    if not ROLLUP.is_file():
        findings.append("missing docs/generated/geos_lane2_residual_evidence.json")

    if findings:
        print("verify_lane2_residuals_on_disk: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_lane2_residuals_on_disk: LANE2_RESIDUALS_ON_DISK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
