#!/usr/bin/env python3
"""Batch 1729 — tenant abrupt-end phased sweep harness + artifact gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

REQUIRED = [
    "scripts/run_tenant_abrupt_end_e2e.mjs",
    "scripts/generate_tenant_surface_coverage_matrix.py",
    "scripts/verify_platform_abrupt_end_sweep.mjs",
    "docs/generated/portal_tenant_sweep_routes.json",
    "docs/generated/preview_tenant_surface_coverage_matrix.html",
]

ARTIFACT = ROOT / "var" / "tenant-abrupt-end-sweep.json"
ROUTES_JSON = ROOT / "docs" / "generated" / "portal_tenant_sweep_routes.json"
EXPECTED_ROUTES = 200


def _run(script: str, *extra: str) -> tuple[int, str]:
    proc = subprocess.run(
        [PY, str(ROOT / script), *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def main() -> int:
    failures: list[str] = []

    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            failures.append(f"missing required file: {rel}")

    code, out = _run("scripts/generate_portal_tenant_sweep_routes.py", "--check")
    if code != 0:
        failures.append(f"portal_tenant_sweep_routes drift ({code})")
        for line in out.splitlines()[-3:]:
            failures.append(f"  {line}")

    code, out = _run("scripts/generate_tenant_surface_coverage_matrix.py", "--check")
    if code != 0:
        failures.append(f"preview_tenant_surface_coverage_matrix drift ({code})")
        for line in out.splitlines()[-3:]:
            failures.append(f"  {line}")

    if ROUTES_JSON.is_file():
        data = json.loads(ROUTES_JSON.read_text(encoding="utf-8"))
        count = int(data.get("count") or len(data.get("routes") or []))
        if count < EXPECTED_ROUTES:
            failures.append(f"route ledger count {count} < {EXPECTED_ROUTES}")

    max_infra = int(os.environ.get("TENANT_SWEEP_MAX_INFRA_SKIP", "0"))

    if not ARTIFACT.is_file():
        failures.append(f"missing artifact {ARTIFACT.relative_to(ROOT)} — run npm run sweep:abrupt-end:tenant:e2e")
    else:
        sweep = json.loads(ARTIFACT.read_text(encoding="utf-8"))
        tenant_tested = int(sweep.get("tenantTested") or 0)
        tenant_planned = int(sweep.get("tenantPlanned") or EXPECTED_ROUTES)
        failed = int(sweep.get("failed") or 0)
        layout_proven = int(sweep.get("layoutProven") or 0)
        infra_skipped = int(sweep.get("infraSkipped") or 0)

        if tenant_tested < tenant_planned:
            failures.append(f"tenantTested={tenant_tested} < tenantPlanned={tenant_planned}")
        if failed != 0:
            failures.append(f"failed={failed} (expected 0)")
        if layout_proven < tenant_planned:
            failures.append(f"layoutProven={layout_proven} < tenantPlanned={tenant_planned}")
        if infra_skipped > max_infra:
            failures.append(f"infraSkipped={infra_skipped} > max {max_infra}")

    if failures:
        print("verify_tenant_abrupt_end_phased_sweep: FAIL")
        for item in failures:
            print(f"- {item}")
        return 1

    print("verify_tenant_abrupt_end_phased_sweep: TENANT_ABRUPT_END_PHASED_SWEEP_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
