#!/usr/bin/env python3
"""Verify tenant performance trust dashboard (T1) wiring."""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REQUIRED = (
    ROOT / "apps/observability/tenant_performance.py",
    ROOT / "apps/schools/views_tenant_performance.py",
    ROOT / "templates/accounts/tenant_performance_dashboard.html",
    ROOT / "static/css/rmc-tenant-performance.css",
)


def main() -> int:
    errors: list[str] = []
    for path in REQUIRED:
        if not path.is_file():
            errors.append(f"missing: {path.relative_to(ROOT)}")

    urls_path = ROOT / "apps/accounts/urls.py"
    urls_text = urls_path.read_text(encoding="utf-8")
    for name in ("tenant_performance_dashboard", "tenant_performance_json"):
        if name not in urls_text:
            errors.append(f"accounts/urls.py missing route name {name}")

    strip_path = ROOT / "templates/partials/tenant/operational_health_strip.html"
    strip = strip_path.read_text(encoding="utf-8")
    if "tenant_performance_dashboard" not in strip:
        errors.append("operational_health_strip missing Performance link")

    proc_nav = ROOT / "templates/marketing/partials/mkt_procurement_trust_nav.html"
    threshold = ROOT / "templates/marketing/threshold_era_home.html"
    if not proc_nav.is_file():
        errors.append("missing marketing procurement trust nav partial")
    elif threshold.is_file():
        threshold_text = threshold.read_text(encoding="utf-8")
        if "mkt_procurement_trust_nav.html" not in threshold_text:
            errors.append("threshold_era_home missing procurement trust nav include")

    for py in (
        ROOT / "apps/observability/tenant_performance.py",
        ROOT / "apps/schools/views_tenant_performance.py",
    ):
        ast.parse(py.read_text(encoding="utf-8"))

    if errors:
        for err in errors:
            print(f"TENANT_PERFORMANCE_T1_FAIL: {err}")
        return 1

    print("TENANT_PERFORMANCE_T1_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
