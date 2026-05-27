#!/usr/bin/env python3
"""Audit tenant registration, enrollment, onboarding, and offboarding workflow wiring."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    ("apps/lifecycle/enrollment_workflow_matrix.py", "build_lifecycle_workflow_hub_payload"),
    ("apps/lifecycle/enrollment_workflow_matrix.py", "REGISTRATION_TRACK"),
    ("apps/lifecycle/enrollment_workflow_matrix.py", "ENROLLMENT_TRACK"),
    ("apps/lifecycle/views_tenant_lifecycle.py", "tenant_lifecycle_command_center"),
    ("apps/lifecycle/views_tenant_lifecycle.py", "api_tenant_lifecycle_hub"),
    ("templates/siteconfig/tenant_lifecycle_command_center.html", "data-rmc-section-anchor"),
    ("templates/siteconfig/tenant_lifecycle_command_center.html", "rmc_section_nav_curated"),
    ("templates/siteconfig/tenant_studio_hub.html", "data-rmc-tenant-studio-lifecycle-hub"),
    ("config/tenant_urls.py", "tenant_lifecycle_command_center"),
    ("config/tenant_urls.py", "api_tenant_lifecycle_hub"),
)


def main() -> int:
    failures: list[str] = []
    for rel, needle in REQUIRED:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing: {rel}")
            continue
        if needle not in path.read_text(encoding="utf-8", errors="replace"):
            failures.append(f"{rel}: missing `{needle}`")

    if failures:
        print("TENANT_LIFECYCLE_WORKFLOW_AUDIT_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("TENANT_LIFECYCLE_WORKFLOW_AUDIT_PASS")
    print(f"  checks: {len(REQUIRED)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
