#!/usr/bin/env python3
"""Audit sidebar accordions / Apps menus for overflow traps that clip expanded items."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/generated/sidebar_disclosure_overflow_audit.json"

TEMPLATE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "admin-model-list-overflow-hidden",
        re.compile(
            r'class="[^"]*admin-sidebar-model-list[^"]*overflow-hidden',
            re.IGNORECASE,
        ),
        "Remove overflow-hidden from admin-sidebar-model-list — clips expanded models",
    ),
)

CSS_FORBIDDEN: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "cp-admin-apps-max-height-trap",
        re.compile(
            r"#cp-admin-sidebar-apps\s*\{[^}]*max-height:\s*min\(",
            re.IGNORECASE | re.DOTALL,
        ),
        "Remove max-height trap on #cp-admin-sidebar-apps — inner rail scroll owns overflow",
    ),
    (
        "cp-sidebar-group-max-height",
        re.compile(
            r"\.cp-sidebar__group(?:\[open\])?\s*\{[^}]*max-height:",
            re.IGNORECASE | re.DOTALL,
        ),
        "cp-sidebar__group must not cap max-height — clips expanded accordion items",
    ),
)

CSS_REQUIRED_SNIPPETS: tuple[str, ...] = (
    "overflow: visible",
    "cp-sidebar__group[open]",
)

SHELL_MARKERS: tuple[tuple[str, str], ...] = (
    ("templates/control_plane_skeleton.html", "rmc_sidebar_disclosure_contract_styles.html"),
    ("templates/admin/base_site.html", "rmc_sidebar_disclosure_contract_styles.html"),
    ("templates/portal_base.html", "rmc_sidebar_disclosure_contract_styles.html"),
)


def _scan_templates() -> list[dict]:
    findings: list[dict] = []
    for rel in ROOT.glob("templates/**/*.html"):
        text = rel.read_text(encoding="utf-8", errors="replace")
        for rule_id, pattern, message in TEMPLATE_PATTERNS:
            if pattern.search(text):
                findings.append(
                    {
                        "rule": rule_id,
                        "file": str(rel.relative_to(ROOT)).replace("\\", "/"),
                        "message": message,
                    }
                )
    return findings


def _scan_css() -> list[dict]:
    findings: list[dict] = []
    contract = ROOT / "static/css/rmc-sidebar-disclosure-contract.css"
    if not contract.is_file():
        findings.append(
            {
                "rule": "missing-contract-css",
                "file": "static/css/rmc-sidebar-disclosure-contract.css",
                "message": "Sidebar disclosure contract stylesheet is missing",
            }
        )
        return findings

    contract_text = contract.read_text(encoding="utf-8")
    for snippet in CSS_REQUIRED_SNIPPETS:
        if snippet not in contract_text:
            findings.append(
                {
                    "rule": "contract-incomplete",
                    "file": "static/css/rmc-sidebar-disclosure-contract.css",
                    "message": f"Contract missing required snippet: {snippet!r}",
                }
            )

    for rel in ROOT.glob("static/css/**/*.css"):
        if rel.name == "rmc-sidebar-disclosure-contract.css":
            continue
        text = rel.read_text(encoding="utf-8", errors="replace")
        for rule_id, pattern, message in CSS_FORBIDDEN:
            if pattern.search(text):
                findings.append(
                    {
                        "rule": rule_id,
                        "file": str(rel.relative_to(ROOT)).replace("\\", "/"),
                        "message": message,
                    }
                )
    return findings


def _scan_shells() -> list[dict]:
    findings: list[dict] = []
    for rel, marker in SHELL_MARKERS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(
                {"rule": "missing-shell", "file": rel, "message": f"Shell template missing: {rel}"}
            )
            continue
        if marker not in path.read_text(encoding="utf-8"):
            findings.append(
                {
                    "rule": "shell-missing-contract",
                    "file": rel,
                    "message": f"{rel} does not load {marker}",
                }
            )
    return findings


def main() -> int:
    findings = _scan_templates() + _scan_css() + _scan_shells()
    report = {
        "finding_count": len(findings),
        "findings": findings,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
        "remediation_status": "PASS" if not findings else "FAIL",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Sidebar disclosure overflow findings: {len(findings)}")
    for item in findings[:20]:
        print(f"  - [{item['rule']}] {item['file']}: {item['message']}")
    if len(findings) > 20:
        print(f"  ... and {len(findings) - 20} more")

    if findings:
        print("SIDEBAR_DISCLOSURE_OVERFLOW_FAIL")
        return 1

    print("SIDEBAR_DISCLOSURE_OVERFLOW_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
