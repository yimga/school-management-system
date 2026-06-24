#!/usr/bin/env python3
"""Gap-closure verifier for competitive-dominance audit items shipped in-repo."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKS: list[tuple[str, Path]] = [
    ("T1 tenant_performance module", ROOT / "apps/observability/tenant_performance.py"),
    ("T1 performance dashboard template", ROOT / "templates/accounts/tenant_performance_dashboard.html"),
    ("T1 performance views", ROOT / "apps/schools/views_tenant_performance.py"),
    ("T2 prometheus alert rules", ROOT / "apps/observability/prometheus_alert_rules.py"),
    ("T2 slo alerts artifact", ROOT / "deploy/observability/slo_alerts.yml"),
    ("T3 observability compose", ROOT / "deploy/observability/docker-compose.yml"),
    ("R2 reconnect rehydrate JS", ROOT / "static/js/rmc-reconnect-rehydrate.js"),
    ("Marketing procurement nav", ROOT / "templates/marketing/partials/mkt_procurement_trust_nav.html"),
    ("O3 offboarding auto-export tests", ROOT / "apps/schools/tests/test_offboarding_auto_export.py"),
]


def main() -> int:
    errors: list[str] = []
    for label, path in CHECKS:
        if not path.is_file():
            errors.append(f"{label}: missing {path.relative_to(ROOT)}")

    urls = (ROOT / "apps/accounts/urls.py").read_text(encoding="utf-8")
    if "tenant_performance_dashboard" not in urls:
        errors.append("accounts/urls.py missing tenant_performance_dashboard")

    threshold = (ROOT / "templates/marketing/threshold_era_home.html").read_text(encoding="utf-8")
    if "mkt_procurement_trust_nav" not in threshold:
        errors.append("threshold_era_home.html missing procurement trust nav include")

    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8")
    if "rmc-reconnect-rehydrate.js" not in portal:
        errors.append("portal_base.html missing rmc-reconnect-rehydrate.js")

    health_js = (ROOT / "static/js/rmc-tenant-health-live.js").read_text(encoding="utf-8")
    if "rmc:reconnect-rehydrate" not in health_js:
        errors.append("rmc-tenant-health-live.js missing reconnect listener")

    for py in (
        ROOT / "apps/observability/tenant_performance.py",
        ROOT / "apps/schools/views_tenant_performance.py",
        ROOT / "apps/observability/prometheus_alert_rules.py",
    ):
        ast.parse(py.read_text(encoding="utf-8"))

    js_path = ROOT / "static/js/rmc-reconnect-rehydrate.js"
    js_text = js_path.read_text(encoding="utf-8")
    if "sync-complete" not in js_text or "rmc:reconnect-rehydrate" not in js_text:
        errors.append("rmc-reconnect-rehydrate.js missing required hooks")

    if errors:
        for err in errors:
            print(f"COMPETITIVE_GAP_CLOSURE_FAIL: {err}")
        return 1

    print("COMPETITIVE_GAP_CLOSURE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
