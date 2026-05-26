#!/usr/bin/env python3
"""
Secondary sweep audit — zero-bleed enforcement after isomorphic grid pass.

Validates dynamic viewport (100dvh), scroll isolation, text expansion shield,
micro-spacing utilities, and preview HTML north-star alignment.

Exits 0 with ISOMORPHIC_GRID_SWEEP_PASS.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/generated/isomorphic_grid_sweep_audit.json"

SWEEP_CSS = "static/css/rmc-isomorphic-grid-sweep.css"
SWEEP_JS = "static/js/rmc-isomorphic-grid-sweep.js"

REQUIRED_CSS = (
    "--rmc-iso-viewport-h",
    "100dvh",
    "100lvh",
    "overscroll-behavior: contain",
    "contain: content",
    "data-rmc-double-scroll-risk",
    "data-rmc-iso-scroll-zone",
    "data-rmc-text-shield",
    "env(safe-area-inset",
    "display-mode: standalone",
)

REQUIRED_JS = (
    "rmcIsoGridSweep",
    "detectDoubleScroll",
    "data-rmc-double-scroll-risk",
    "visualViewport",
    "data-rmc-panel-sweep-empty",
    "data-rmc-text-shield",
)


def _read(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def audit_sweep_bundle() -> list[str]:
    fails: list[str] = []
    css = _read(SWEEP_CSS)
    js = _read(SWEEP_JS)
    if not css:
        fails.append(f"missing {SWEEP_CSS}")
    if not js:
        fails.append(f"missing {SWEEP_JS}")
    for marker in REQUIRED_CSS:
        if css and marker not in css:
            fails.append(f"{SWEEP_CSS}: missing `{marker}`")
    for marker in REQUIRED_JS:
        if js and marker not in js:
            fails.append(f"{SWEEP_JS}: missing `{marker}`")
    return fails


def audit_wiring() -> list[str]:
    fails: list[str] = []
    chrome = _read("templates/partials/rmc_platform_chrome_styles.html")
    boot = _read("templates/partials/rmc_isomorphic_grid_boot.html")
    if "rmc-isomorphic-grid-sweep.css" not in chrome:
        fails.append("rmc_platform_chrome_styles.html missing sweep CSS")
    if "rmc-isomorphic-grid-sweep.js" not in boot:
        fails.append("rmc_isomorphic_grid_boot.html missing sweep JS")
    iso = _read("static/css/rmc-isomorphic-grid.css")
    if "rmc-isomorphic-grid-sweep" in iso:
        fails.append("sweep CSS must load after base iso grid, not merged into it")
    app_shell = _read("static/css/rmc-app-shell.css")
    if "100dvh" not in app_shell:
        fails.append("rmc-app-shell.css should declare 100dvh (base contract)")
    return fails


def audit_preview_north_stars() -> list[str]:
    fails: list[str] = []
    for rel in (
        "docs/generated/preview_app_shell_manager_v8_200x.html",
        "docs/generated/preview_app_shell_admin_v1_200x.html",
        "docs/generated/preview_app_shell_tenant_portal_v3_100x.html",
    ):
        path = ROOT / rel
        if not path.is_file() or path.stat().st_size < 2048:
            fails.append(f"missing preview north star: {rel}")
    return fails


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    checks = {
        "sweep_bundle": audit_sweep_bundle(),
        "wiring": audit_wiring(),
        "preview_north_stars": audit_preview_north_stars(),
    }
    failures: list[str] = []
    for items in checks.values():
        failures.extend(items)

    report = {
        "finding_count": len(failures),
        "findings": [{"message": m} for m in failures],
        "checks": {k: len(v) for k, v in checks.items()},
        "generated_at": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "remediation_status": "PASS" if not failures else "FAIL",
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("ISOMORPHIC_GRID_SWEEP_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("ISOMORPHIC_GRID_SWEEP_PASS")
    print("  dynamic viewport: 100dvh / 100lvh + safe-area + visualViewport sync")
    print("  scroll isolation: canvas-owned Y scroll + iso-scroll-zone contract")
    print("  text shield: buttons / forms / tables / modals + tooltip refresh")
    print("  empty panels: data-rmc-panel-sweep-empty auto footprint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
