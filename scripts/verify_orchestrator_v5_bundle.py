#!/usr/bin/env python3
"""Master validation for orchestrator v5 transformational pack."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "orchestrator_v5_bundle_audit.json"

CHECKS: list[tuple[str, list[str]]] = [
    ("journey_manifest", [sys.executable, "scripts/generate_orchestrator_journey_manifest.py"]),
    (
        "journey_coverage",
        [sys.executable, "scripts/verify_stage_journey_coverage.py"],
    ),
    (
        "nav_ledger",
        [sys.executable, "scripts/verify_nav_resolves_to_named_route.py", "--strict"],
    ),
    (
        "interaction_contract",
        [sys.executable, "scripts/verify_interaction_integrity_contract.py"],
    ),
    (
        "prompt_pack",
        [sys.executable, "scripts/verify_orchestrator_prompt_pack.py", "--strict"],
    ),
]


def main() -> int:
    results: list[dict] = []
    for name, cmd in CHECKS:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
        ok = proc.returncode == 0
        tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        proof = tail[-1] if tail else f"exit {proc.returncode}"
        results.append({"check": name, "ok": ok, "proof": proof[:200]})

    manifest = ROOT / "docs" / "generated" / "orchestrator_journey_manifest.json"
    journey_ok = False
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        journey_ok = int(data.get("journey_count") or 0) == 27

    results.append(
        {
            "check": "journey_count_27",
            "ok": journey_ok,
            "proof": "27 journeys" if journey_ok else "manifest count != 27",
        }
    )

    fail = [r for r in results if not r["ok"]]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_pack_version": "2026-05-20-orchestrator-v5",
        "verdict": "ORCHESTRATOR_V5_BUNDLE_PASS" if not fail else "ORCHESTRATOR_V5_BUNDLE_FAIL",
        "checks": results,
        "failures": [r["check"] for r in fail],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if fail:
        print(f"ORCHESTRATOR_V5_BUNDLE_FAIL ({len(fail)} failures)")
        for r in fail:
            print(f"  - {r['check']}: {r['proof']}")
        return 1
    print(f"ORCHESTRATOR_V5_BUNDLE_PASS ({len(results)} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
