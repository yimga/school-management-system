#!/usr/bin/env python3
"""
Five-phase data visualization prompt — completion gate.

Runs file-existence checks, platform surface wiring, npm audit/tests, and seeder CLI.
Writes docs/generated/analytics_viz_prompt_completion.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "analytics_viz_prompt_completion.json"


@dataclass
class Row:
    phase: str
    check_id: str
    status: str
    proof: str


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _npm_cmd(*args: str) -> list[str]:
    import shutil

    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        return ["npm", *args]
    return [npm, *args]


def _tsx_cmd(*args: str) -> list[str]:
    import sys

    name = "tsx.cmd" if sys.platform == "win32" else "tsx"
    return [str(ROOT / "node_modules" / ".bin" / name), *args]


def _vitest_cmd(*args: str) -> list[str]:
    import sys

    name = "vitest.cmd" if sys.platform == "win32" else "vitest"
    return [str(ROOT / "node_modules" / ".bin" / name), *args]


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    import sys

    kwargs = {
        "cwd": str(ROOT),
        "capture_output": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
    }
    if sys.platform == "win32":
        proc = subprocess.run(subprocess.list2cmdline(cmd), **kwargs, shell=True)
    else:
        proc = subprocess.run(cmd, **kwargs, shell=False)
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    return proc.returncode, out[-800:]


def main() -> int:
    rows: list[Row] = []

    def add(phase: str, check_id: str, ok: bool, proof: str) -> None:
        rows.append(Row(phase, check_id, "PASS" if ok else "FAIL", proof))

    # Phase 1 — core library
    phase1_files = [
        "src/components/shared/analytics/PlatformPulseLineChart.tsx",
        "src/components/shared/analytics/MetricKpiCard.tsx",
        "src/components/shared/analytics/ResourceAllocationDonut.tsx",
        "src/components/shared/analytics/icons/PlatformIcon.tsx",
        "static/css/rmc-analytics-viz.css",
    ]
    add("1", "core_components", all(_exists(p) for p in phase1_files), ", ".join(phase1_files))

    icon_src = _read("src/components/shared/analytics/icons/PlatformIcon.tsx")
    add(
        "1",
        "icon_aria",
        "aria-label" in icon_src and "strokeWidth" in icon_src,
        "PlatformIcon aria-label + strokeWidth",
    )

    # Phase 2 — tenant dashboard
    phase2_files = [
        "src/apps/dashboard/TenantOverview.tsx",
        "src/apps/dashboard/ErrorBoundary.tsx",
        "src/components/shared/analytics/skeletons/AnalyticsSkeletons.tsx",
    ]
    add("2", "orchestrator", all(_exists(p) for p in phase2_files), ", ".join(phase2_files))
    to_src = _read("src/apps/dashboard/TenantOverview.tsx")
    add("2", "error_boundary", "VizErrorBoundary" in to_src, "per-widget VizErrorBoundary")
    add("2", "tenant_id", "tenantId: string" in to_src, "tenantId prop")

    # Phase 3 — seeder
    add("3", "seeder_module", _exists("src/database/seeds/analytics-seeder.ts"), "analytics-seeder.ts")
    add("3", "seeder_cli", _exists("src/database/seeds/run-analytics-seed.ts"), "run-analytics-seed.ts")
    code, tail = _run(_tsx_cmd("src/database/seeds/run-analytics-seed.ts", "audit-tenant"))
    add("3", "seeder_cli_run", code == 0 and "SEED OK" in tail, tail or "missing SEED OK")

    # Phase 4 — forensic audit
    code, tail = _run(_npm_cmd("run", "audit:analytics-viz"))
    add("4", "forensic_audit", code == 0 and "AUDIT PASS" in tail, tail or "audit failed")

    # Phase 5 — tests
    add("5", "test_ts", _exists("src/components/shared/analytics/analytics.test.ts"), "analytics.test.ts")
    add("5", "test_tsx", _exists("src/components/shared/analytics/analytics.test.tsx"), "analytics.test.tsx")
    code, tail = _run(_vitest_cmd("run"))
    add("5", "vitest", code == 0, tail or "vitest failed")

    # Platform surfaces (marketing + tenant + operator KPI)
    bundle = _exists("static/js/dist/rmc-analytics-dashboard.iife.js")
    add("platform", "iife_bundle", bundle, "static/js/dist/rmc-analytics-dashboard.iife.js")

    surfaces = {
        "control_plane": "templates/schools/super_analytics_overview.html",
        "tenant_insights": "templates/analytics/dashboard.html",
        "operator_kpi": "templates/schoolops/operator/meal_plan_analytics.html",
        "marketing_mockup": "templates/marketing/components/_hero_live_campus_pulse.html",
    }
    for name, path in surfaces.items():
        text = _read(path) if _exists(path) else ""
        ok = "data-rmc-tenant-overview" in text or 'include "partials/rmc_analytics_viz_mount.html"' in text
        add("platform", f"surface_{name}", ok, path)

    partial_ok = all(
        _exists(p)
        for p in (
            "templates/partials/rmc_analytics_viz_mount.html",
            "templates/partials/rmc_analytics_viz_assets.html",
            "templates/partials/rmc_analytics_viz_bundle.html",
        )
    )
    add("platform", "shared_partials", partial_ok, "rmc_analytics_viz_* partials")

    fail_count = sum(1 for r in rows if r.status == "FAIL")
    payload = {
        "verdict": "ANALYTICS_VIZ_PROMPT_PASS" if fail_count == 0 else "ANALYTICS_VIZ_PROMPT_FAIL",
        "pass_count": sum(1 for r in rows if r.status == "PASS"),
        "fail_count": fail_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": [
            {"phase": r.phase, "check_id": r.check_id, "status": r.status, "proof": r.proof}
            for r in rows
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(payload["verdict"], f"({payload['pass_count']}/{len(rows)} checks)")
    for r in rows:
        if r.status == "FAIL":
            print(f"  FAIL [{r.phase}] {r.check_id}: {r.proof}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
