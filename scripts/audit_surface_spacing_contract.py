#!/usr/bin/env python3
"""Audit spacing contract across /super/, /admin/, and tenant templates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

ARCHETYPE = 'data-page-archetype="operational-workbench"'
WORKBENCH = 'data-rmc-operational-workbench="1"'
FRAME = "rmc_operational_center_frame.html"
HERO = "world_class_page_hero.html"
FRAME_CSS = "rmc-operational-center-frame.css"
SPACING_CSS = "rmc-surface-spacing-contract.css"

ALLOW_HERO = {
    "templates/schools/super_dashboard.html",
    "templates/customersuccess/super_dashboard.html",
}
ALLOW_LANDING = ALLOW_HERO

CP_ROOTS = (
    "templates/schools/super_",
    "templates/marketplace/",
    "templates/platform_runtime/",
    "templates/observability/",
    "templates/orchestration/",
    "templates/customersuccess/",
    "templates/schools/billing_dashboard.html",
    "templates/migration_cloud/",
)

TENANT_BACKEND_ROOTS = (
    "templates/finance/",
    "templates/people/",
    "templates/schoolops/",
    "templates/feedback/help_center.html",
    "templates/platform_runtime/tenant_",
    "templates/platform_runtime/school_configuration",
    "templates/marketplace/tenant_",
)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _surface(path: Path) -> str:
    rel = _rel(path)
    if rel.startswith("templates/admin/"):
        return "admin"
    if any(rel.startswith(p) for p in CP_ROOTS) or "control_plane" in rel:
        return "super"
    if rel.startswith("templates/marketing/"):
        return "marketing"
    return "tenant"


def scan() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = _rel(path)
        if "partials/" in rel and "document_library" not in rel:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        surface = _surface(path)

        if ARCHETYPE in text and WORKBENCH not in text and rel not in ALLOW_LANDING:
            findings.append(
                {
                    "file": rel,
                    "surface": surface,
                    "issue": "missing_workbench_marker",
                    "severity": "medium",
                }
            )

        if ARCHETYPE in text or WORKBENCH in text:
            if "container-fluid py-4" in text and 'data-rmc-density="open"' not in text:
                if rel in ALLOW_LANDING:
                    continue
                if surface in ("super", "tenant") and "wizard" not in rel.lower():
                    findings.append(
                        {
                            "file": rel,
                            "surface": surface,
                            "issue": "operational_py4_padding",
                            "severity": "low",
                        }
                    )

        if surface == "super" and ARCHETYPE in text:
            if FRAME not in text and HERO not in text and rel not in ALLOW_LANDING:
                if "extends \"control_plane_base" in text or "control_plane_shell" in text:
                    findings.append(
                        {
                            "file": rel,
                            "surface": surface,
                            "issue": "no_steering_frame_or_hero",
                            "severity": "low",
                        }
                    )

        if surface == "tenant" and (ARCHETYPE in text or WORKBENCH in text):
            if FRAME_CSS not in text and "extends \"portal_base" not in rel:
                if "extends \"backend_base" in text or "extends \"portal_base" in text:
                    pass  # shell loads CSS globally after this wave
            if HERO in text and FRAME in text:
                findings.append(
                    {
                        "file": rel,
                        "surface": surface,
                        "issue": "hero_and_frame_duplicate",
                        "severity": "high",
                    }
                )

        if 'style="' in text and re.search(r'style="[^"]*(?:^|[;])\s*padding\s*:', text):
            if surface == "tenant" and rel.startswith("templates/accounts/"):
                if rel.startswith("templates/accounts/email/"):
                    continue
                if "inline-style-allow:" in text:
                    continue
                if "rmc-account-surface.css" in text:
                    continue
                if re.search(r'style="[^"]*padding[^"]*inline-style-allow:', text):
                    continue
                findings.append(
                    {
                        "file": rel,
                        "surface": surface,
                        "issue": "inline_padding_accounts",
                        "severity": "low",
                    }
                )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true", help="Write docs/generated/surface_spacing_contract_audit.json")
    parser.add_argument("--strict", action="store_true", help="Fail on medium+ severity")
    args = parser.parse_args()
    findings = scan()
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]
    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": len(findings),
                    "high": len(high),
                    "medium": len(medium),
                    "findings": findings,
                },
                indent=2,
            )
        )
    else:
        print(f"surface-spacing-contract: {len(findings)} finding(s) ({len(high)} high, {len(medium)} medium)")
        for row in findings[:80]:
            print(f"  [{row['severity']}] {row['surface']} {row['issue']}: {row['file']}")
        if len(findings) > 80:
            print(f"  ... and {len(findings) - 80} more")
    if args.write:
        out = ROOT / "docs" / "generated" / "surface_spacing_contract_audit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "finding_count": len(findings),
                    "high": len(high),
                    "medium": len(medium),
                    "findings": findings,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if args.strict and (high or medium):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
