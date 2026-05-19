#!/usr/bin/env python3
"""Gear-up items 1–6 completion gate for unified analytics viz."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "analytics_viz_gear_up_completion.json"


@dataclass
class Row:
    item: str
    check_id: str
    status: str
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
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
    py = sys.executable

    def add(item: str, check_id: str, ok: bool, proof: str) -> None:
        rows.append(Row(item, check_id, "PASS" if ok else "FAIL", proof))

    # 1 — Real data API
    add(
        "1",
        "api_module",
        _exists("apps/api/analytics_viz_api.py"),
        "apps/api/analytics_viz_api.py",
    )
    add(
        "1",
        "service_module",
        _exists("apps/analytics/services/tenant_overview_viz.py"),
        "tenant_overview_viz.py",
    )
    urls = _read("apps/api/urls.py")
    add(
        "1",
        "url_registered",
        "internal/analytics-viz/overview/" in urls and "api-analytics-viz-overview" in urls,
        "apps/api/urls.py",
    )
    code, tail = _run(
        [
            py,
            "scripts/run_sqlite_memory_tests.py",
            "apps.api.tests.test_analytics_viz_api",
            "apps.analytics.tests.test_tenant_overview_viz",
            "apps.siteconfig.tests.test_analytics_viz_context",
        ],
        timeout=600,
    )
    add("1", "django_tests", code == 0, tail or "django tests")

    # 2 — Performance / CI
    add(
        "2",
        "lazy_loader",
        _exists("static/js/rmc-analytics-viz-loader.js"),
        "rmc-analytics-viz-loader.js",
    )
    bundle_partial = _read("templates/partials/rmc_analytics_viz_bundle.html")
    add(
        "2",
        "lazy_bundle_partial",
        "rmc-analytics-viz-loader.js" in bundle_partial,
        "bundle partial uses loader",
    )
    add(
        "2",
        "ci_workflow",
        _exists(".github/workflows/analytics-viz.yml"),
        ".github/workflows/analytics-viz.yml",
    )
    pkg = _read("package.json")
    add(
        "2",
        "verify_analytics_script",
        "verify_analytics_viz_gear_up.py" in pkg or "verify:analytics" in pkg,
        "package.json verify:analytics",
    )

    # 3 — Chart system bridge
    charts = _read("static/js/dashboard-charts-shared.js")
    add(
        "3",
        "unified_palette_bridge",
        "getUnifiedVizPalette" in charts,
        "DashboardChartsShared.getUnifiedVizPalette",
    )

    # 4 — E2E a11y spec file
    add(
        "4",
        "playwright_spec",
        _exists("tests/e2e/analytics-viz-a11y.spec.js"),
        "tests/e2e/analytics-viz-a11y.spec.js",
    )

    # 5 — Product (fetch, toolbar, flag)
    to_src = _read("src/apps/dashboard/TenantOverview.tsx")
    add("5", "date_range_ui", 'type="date"' in to_src, "date inputs")
    add("5", "compare_ui", "compare" in to_src.lower(), "compare period")
    add("5", "export_csv", "Export CSV" in to_src, "CSV export")
    fetch_src = _read("src/apps/dashboard/fetchTenantBundle.ts")
    add("5", "api_fetch", "fetch(" in fetch_src and "apiUrl" in fetch_src, "fetchTenantBundle")
    flags = _read("apps/siteconfig/models_support.py")
    add(
        "5",
        "feature_flag",
        "enable_unified_analytics_viz" in flags,
        "default_backend_feature_flags",
    )
    cp = _read("apps/siteconfig/context_processors.py")
    add("5", "context_processor", "analytics_viz_context" in cp, "analytics_viz_context")
    settings = _read("config/settings.py")
    add(
        "5",
        "settings_cp",
        "analytics_viz_context" in settings,
        "settings context_processors",
    )

    # 6 — Governance
    add(
        "6",
        "mgmt_seed_command",
        _exists("apps/analytics/management/commands/seed_analytics_demo.py"),
        "seed_analytics_demo",
    )
    code, _tail = _run([py, "manage.py", "seed_analytics_demo", "audit-tenant", "--validate"])
    add("6", "seed_command_run", code == 0, "exit 0" if code == 0 else _tail or "seed command")
    sot = _read("docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md")
    add(
        "6",
        "sot_row",
        "unified analytics viz gear-up" in sot.lower() or "analytics viz gear-up" in sot.lower(),
        "SOT §11.4 row",
    )
    log = _read("docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md")
    add(
        "6",
        "autonomous_log",
        "analytics viz gear-up" in log.lower() or "unified analytics viz" in log.lower(),
        "autonomous log",
    )

    mkt = _read("templates/schools/marketing_landing_v2.html")
    bundle_partial = _read("templates/partials/rmc_analytics_viz_bundle.html")
    add(
        "2",
        "marketing_lazy_not_eager",
        "rmc_analytics_viz_bundle.html" in mkt
        and "rmc-analytics-dashboard.iife.js" not in mkt
        and "rmc-analytics-viz-loader.js" in bundle_partial,
        "marketing_landing_v2 uses lazy bundle partial",
    )
    api_doc = _read("docs/INTERNAL_API_STANDARDS.md")
    add(
        "1",
        "internal_api_doc",
        "internal/analytics-viz/overview/" in api_doc,
        "INTERNAL_API_STANDARDS.md",
    )
    fail_count = sum(1 for r in rows if r.status == "FAIL")
    payload = {
        "verdict": "ANALYTICS_VIZ_GEAR_UP_PASS" if fail_count == 0 else "ANALYTICS_VIZ_GEAR_UP_FAIL",
        "pass_count": sum(1 for r in rows if r.status == "PASS"),
        "fail_count": fail_count,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": [
            {"item": r.item, "check_id": r.check_id, "status": r.status, "proof": r.proof}
            for r in rows
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(payload["verdict"], f"({payload['pass_count']}/{len(rows)} checks)")
    for r in rows:
        if r.status == "FAIL":
            print(f"  FAIL [{r.item}] {r.check_id}: {r.proof}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
