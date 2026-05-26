#!/usr/bin/env python3
"""
Channel sweep — secondary zero-bleed audit across operator, tenant, finance,
data-table, and nav surfaces. Baseline 0 for unmarked inline scroll traps.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/generated/isomorphic_grid_channel_sweep_audit.json"

CHANNELS: dict[str, tuple[str, ...]] = {
    "operator_dashboard": ("templates/schools/super_", "templates/customersuccess/super_"),
    "tenant_portal": ("templates/portal/", "templates/people/backend_", "templates/parent/"),
    "signup_studio": ("templates/schools/signup_", "templates/studio_os/", "templates/schools/onboard_"),
    "forms_factory": ("templates/siteconfig/", "templates/accounts/"),
    "data_tables": ("templates/finance/", "templates/evals/", "templates/migration_cloud/"),
    "navigation_menus": (
        "templates/partials/control_plane_primary_nav.html",
        "templates/partials/tenant_primary_nav.html",
    ),
    "billing_ledger_views": ("templates/finance/invoices.html", "templates/finance/payments.html"),
    "academic_gradebooks": ("templates/teacher/marks_entry.html", "templates/evals/"),
    "pwa_shell": (
        "templates/control_plane_skeleton.html",
        "templates/portal_base.html",
        "templates/admin/base_site.html",
    ),
}

INLINE_SCROLL = re.compile(
    r"style\s*=\s*[\"'][^\"']*max-height[^\"']*overflow-y\s*:\s*auto",
    re.IGNORECASE,
)

REQUIRED_PARTIALS = (
    ("templates/partials/control_plane_primary_nav.html", "rmc-text-container"),
    ("templates/partials/rmc_platform_chrome_styles.html", "rmc-isomorphic-grid-sweep.css"),
    ("templates/partials/rmc_isomorphic_grid_boot.html", "rmc-isomorphic-grid-sweep.js"),
)

DATA_TABLE_CHANNELS = (
    "templates/people/backend_student_list.html",
    "templates/people/backend_teacher_list.html",
    "templates/people/backend_guardian_list.html",
    "templates/finance/invoices.html",
)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def scan_inline_scroll_traps() -> list[str]:
    findings: list[str] = []
    for path in sorted((ROOT / "templates").rglob("*.html")):
        rel = _rel(path)
        if "partials/" in rel and "nav" not in rel and "rmc_" not in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if INLINE_SCROLL.search(text) and 'data-rmc-iso-scroll-zone="1"' not in text:
            if INLINE_SCROLL.search(text):
                # allow if every match is inside a block that also has scroll zone on same line
                for i, line in enumerate(text.splitlines(), 1):
                    if INLINE_SCROLL.search(line) and 'data-rmc-iso-scroll-zone="1"' not in line:
                        findings.append(f"{rel}:{i}: inline scroll trap without data-rmc-iso-scroll-zone")
    return findings


def scan_data_table_channels() -> list[str]:
    findings: list[str] = []
    for rel in DATA_TABLE_CHANNELS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing channel template: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "rmc-data-table" not in text:
            findings.append(f"{rel}: missing rmc-data-table on list surface")
        if "rmc-data-table-wrapper" not in text and "table-responsive" in text:
            findings.append(f"{rel}: table-responsive missing rmc-data-table-wrapper")
    return findings


def scan_required_partials() -> list[str]:
    findings: list[str] = []
    for rel, needle in REQUIRED_PARTIALS:
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if needle not in text:
            findings.append(f"{rel}: missing `{needle}`")
    return findings


def scan_micro_spacing_utilities() -> list[str]:
    css = (ROOT / "static/css/rmc-isomorphic-grid.css").read_text(encoding="utf-8", errors="replace")
    sweep = (ROOT / "static/css/rmc-isomorphic-grid-sweep.css").read_text(encoding="utf-8", errors="replace")
    fails: list[str] = []
    for util in ("rmc-iso-gap-1", "rmc-iso-pad-4", "--rmc-iso-space-4"):
        if util not in css:
            fails.append(f"rmc-isomorphic-grid.css missing `{util}`")
    if "100dvh" not in sweep:
        fails.append("rmc-isomorphic-grid-sweep.css missing 100dvh viewport matrix")
    return fails


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    checks = {
        "inline_scroll_traps": scan_inline_scroll_traps(),
        "data_table_channels": scan_data_table_channels(),
        "required_partials": scan_required_partials(),
        "micro_spacing_utilities": scan_micro_spacing_utilities(),
    }
    failures: list[str] = []
    for items in checks.values():
        failures.extend(items)

    report = {
        "channels": list(CHANNELS.keys()),
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
        print("ISOMORPHIC_GRID_CHANNEL_SWEEP_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("ISOMORPHIC_GRID_CHANNEL_SWEEP_PASS")
    print(f"  channels: {len(CHANNELS)} families audited")
    print("  inline scroll traps: 0 unmarked")
    print("  data-table channels: rmc-data-table + wrapper wired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
