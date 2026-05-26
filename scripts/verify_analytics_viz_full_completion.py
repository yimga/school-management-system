#!/usr/bin/env python3
"""Master gate: five-phase prompt + gear-up + no eager-IIFE drift."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "analytics_viz_full_completion.json"


def _run(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out[-1200:]


def main() -> int:
    py = sys.executable
    rows: list[dict] = []

    def add(check_id: str, ok: bool, proof: str) -> None:
        rows.append({"check_id": check_id, "status": "PASS" if ok else "FAIL", "proof": proof})

    code, tail = _run(["npm", "run", "verify:analytics"], timeout=600)
    add("verify_analytics_npm", code == 0, tail or "npm run verify:analytics")

    for name, script in (
        ("prompt_completion", "verify_analytics_viz_prompt_completion.py"),
        ("gear_up", "verify_analytics_viz_gear_up.py"),
    ):
        c, t = _run([py, f"scripts/{script}"])
        add(name, c == 0, t.splitlines()[-1] if t else script)

    templates = [
        "templates/schools/marketing_landing_v2.html",
        "templates/schools/super_analytics_overview.html",
        "templates/analytics/dashboard.html",
        "templates/schoolops/operator/meal_plan_analytics.html",
    ]
    drift = []
    for rel in templates:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if "rmc-analytics-dashboard.iife.js" in text and "rmc_analytics_viz_bundle.html" not in text:
            drift.append(rel)
    add("no_eager_iife_templates", not drift, ", ".join(drift) or "all surfaces lazy")

    fail = sum(1 for r in rows if r["status"] == "FAIL")
    payload = {
        "verdict": "ANALYTICS_VIZ_FULL_PASS" if fail == 0 else "ANALYTICS_VIZ_FULL_FAIL",
        "pass_count": sum(1 for r in rows if r["status"] == "PASS"),
        "fail_count": fail,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(payload["verdict"], f"({payload['pass_count']}/{len(rows)})")
    for r in rows:
        if r["status"] == "FAIL":
            print(f"  FAIL {r['check_id']}: {r['proof'][:200]}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
