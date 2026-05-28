#!/usr/bin/env python3
"""Batch 1516 — tenant CSV onboarding wiring verifier."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []

    kernel = ROOT / "apps/customersuccess/bulk_csv_student_import.py"
    if not kernel.is_file():
        findings.append("missing apps/customersuccess/bulk_csv_student_import.py")

    services = _read("apps/customersuccess/services.py")
    for needle in ("student_csv_import", "guardian_invite", "post_fees"):
        if f'"{needle}"' not in services and f"'{needle}'" not in services:
            findings.append(f"services.py missing step key {needle}")

    views = _read("apps/customersuccess/views_tenant.py")
    for fn in ("guided_onboarding_csv_dry_run", "guided_onboarding_csv_apply"):
        if f"def {fn}" not in views:
            findings.append(f"views_tenant.py missing {fn}")

    urls = _read("apps/siteconfig/urls.py")
    for name in ("guided_onboarding_csv_dry_run", "guided_onboarding_csv_apply"):
        if f'name="{name}"' not in urls:
            findings.append(f"siteconfig urls missing {name}")

    template = _read("templates/customersuccess/guided_onboarding.html")
    for needle in ("student-csv-import", "rmc-csv-dry-run", "rmc-csv-apply"):
        if needle not in template:
            findings.append(f"guided_onboarding.html missing {needle}")

    studio = _read("apps/setup_studio/services.py")
    if "student-csv-import" not in studio:
        findings.append("setup_studio data_path missing student-csv-import fragment")

    js = _read("static/js/_pages/customersuccess__guided_onboarding.js")
    if "rmc-csv-dry-run" not in js:
        findings.append("guided_onboarding.js missing CSV import handlers")

    if findings:
        print("TENANT_ONBOARDING_CSV_IMPORT_FAIL")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("TENANT_ONBOARDING_CSV_IMPORT_PASS")
    print("  kernel + guided steps + CSV dry-run/apply + Setup Studio embed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
