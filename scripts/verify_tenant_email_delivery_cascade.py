#!/usr/bin/env python3
"""SODP tenant email cascade gate."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    for rel in (
        "apps/schools/email_delivery_settings.py",
        "apps/schoolops/notification_intent.py",
        "templates/schools/studio/infrastructure_email.html",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    delivery = (ROOT / "apps/schoolops/email_delivery.py").read_text(encoding="utf-8", errors="replace")
    if "def get_resolved_smtp_config(*, school=None)" not in delivery:
        if "school=None" not in delivery.split("def get_resolved_smtp_config", 1)[-1][:120]:
            findings.append("get_resolved_smtp_config missing school= cascade")
    if "_load_tenant_school_override" not in delivery:
        findings.append("missing _load_tenant_school_override")

    infra = (ROOT / "templates/schools/studio/infrastructure_email.html").read_text(
        encoding="utf-8", errors="replace"
    )
    has_password_field = (
        'type="password"' in infra
        or "rmc_password_field.html" in infra
        or "host_password" in infra
    )
    if not has_password_field:
        findings.append("tenant email form missing password field")

    forms = (ROOT / "apps/schoolops/forms_email_delivery.py").read_text(encoding="utf-8", errors="replace")
    if "allow_tenant_email_delivery_override" not in forms:
        findings.append("operator form missing allow_tenant_email_delivery_override")

    if findings:
        print("verify_tenant_email_delivery_cascade: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_tenant_email_delivery_cascade: TENANT_EMAIL_DELIVERY_CASCADE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
