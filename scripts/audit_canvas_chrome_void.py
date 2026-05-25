#!/usr/bin/env python3
"""
Audit canvas chrome voids + deprecated security inline banner on CP/admin/portal.

Exits 0 with CANVAS_CHROME_VOID_PASS when:
- No live _security_posture_banner markup (deprecated partial empty)
- No container-fluid py-4 on control_plane_base extenders (except wizard allowlist)
- No content-max-* on super/admin CP templates
- control_plane_base does not duplicate cockpit breadcrumb + block breadcrumbs
- rmc-canvas-chrome-compact.css wired on shell heads
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
OUT = ROOT / "docs/generated/canvas_chrome_void_audit.json"
COMPACT_CSS = ROOT / "static/css/rmc-canvas-chrome-compact.css"
LEGACY_BANNER = TEMPLATES / "accounts/partials/_security_posture_banner.html"
CP_BASE = TEMPLATES / "control_plane_base.html"
LAYOUT_PARTIAL = TEMPLATES / "partials/rmc_security_posture_layout_styles.html"

WIZARD_ALLOW = (
    "super_create_school_wizard",
    "guided_onboarding",
    "setup-studio",
    "onboard",
)
EXTENDS_CP = re.compile(r'extends\s+["\']control_plane_base\.html["\']', re.I)
CONTENT_MAX = re.compile(r"\bcontent-max-(?:520|640|960|1200|narrow)\b")


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


def audit_legacy_banner() -> list[str]:
    fails = []
    text = LEGACY_BANNER.read_text(encoding="utf-8", errors="replace")
    if "rmc-security-posture-banner" in text or "Account below minimum" in text:
        fails.append("legacy _security_posture_banner still contains live markup")
    return fails


def audit_cp_base_breadcrumb_dup() -> list[str]:
    fails: list[str] = []
    text = CP_BASE.read_text(encoding="utf-8", errors="replace")
    if 'include "partials/cockpit/_breadcrumb.html"' in text:
        fails.append("control_plane_base still includes cockpit/_breadcrumb (duplicate risk)")
    return fails


def audit_compact_css_wired() -> list[str]:
    fails = []
    if not COMPACT_CSS.is_file():
        fails.append("missing rmc-canvas-chrome-compact.css")
        return fails
    partial = LAYOUT_PARTIAL.read_text(encoding="utf-8", errors="replace")
    if "rmc-canvas-chrome-compact.css" not in partial:
        fails.append("rmc_security_posture_layout_styles missing compact CSS link")
    return fails


def audit_cp_templates() -> list[str]:
    fails = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not EXTENDS_CP.search(text):
            continue
        rel = _rel(path)
        if "container-fluid py-4" in text:
            if not any(w in rel.lower() for w in WIZARD_ALLOW):
                fails.append(f"CP template still has py-4: {rel}")
        if CONTENT_MAX.search(text):
            fails.append(f"CP template has content-max clamp: {rel}")
        if 'include "accounts/partials/_security_posture_banner.html"' in text:
            fails.append(f"direct legacy banner include: {rel}")
    return fails


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    checks = {
        "legacy_banner": audit_legacy_banner(),
        "cp_base_breadcrumb": audit_cp_base_breadcrumb_dup(),
        "compact_css": audit_compact_css_wired(),
        "cp_templates": audit_cp_templates(),
    }
    failures: list[str] = []
    for items in checks.values():
        failures.extend(items)

    report = {
        "finding_count": len(failures),
        "findings": [{"message": f} for f in failures],
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
        print("CANVAS_CHROME_VOID_FAIL")
        for f in failures:
            print(f"  - {f}")
    else:
        print("CANVAS_CHROME_VOID_PASS")

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
