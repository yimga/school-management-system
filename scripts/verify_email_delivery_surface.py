#!/usr/bin/env python3
"""GEOS-99 DailyOps gate: email delivery operator surface (batch 1377 / 1389)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = ROOT / rel
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def main() -> int:
    findings: list[str] = []

    for rel in (
        "apps/schoolops/email_delivery.py",
        "apps/schoolops/models_email_delivery.py",
        "apps/schoolops/views_email_health.py",
        "apps/schoolops/views_email_admin.py",
        "apps/schoolops/notification_intent.py",
        "apps/schools/email_delivery_settings.py",
        "apps/schools/views_infrastructure.py",
        "apps/schools/views_signup_diagnostics.py",
        "templates/schoolops/super/email_health.html",
        "templates/schoolops/super/signup_diagnostics.html",
        "templates/schools/studio/infrastructure_email.html",
        "docs/EMAIL_DELIVERABILITY.md",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    mig = ROOT / "apps/schoolops/migrations/0014_email_delivery_event.py"
    if not mig.is_file():
        findings.append("missing migration 0014_email_delivery_event")

    urls = _text("apps/schools/super_urls.py")
    for name in ("email_health", "email_health_probe", "signup_diagnostics"):
        if f'name="{name}"' not in urls:
            findings.append(f"super_urls missing {name}")

    models = _text("apps/schoolops/models_email_delivery.py")
    if "class EmailDeliveryEvent" not in models:
        findings.append("EmailDeliveryEvent model missing")

    delivery = _text("apps/schoolops/email_delivery.py")
    if "def send_transactional" not in delivery:
        findings.append("send_transactional missing")
    if "_load_tenant_school_override" not in delivery:
        findings.append("tenant SMTP cascade missing")
    if "school=None" not in delivery.split("def get_resolved_smtp_config", 1)[-1][:120]:
        findings.append("get_resolved_smtp_config missing school= parameter")

    signup = _text("apps/schools/signup_views.py")
    if "async_send=True" not in signup and "async_send = True" not in signup:
        findings.append("signup welcome path missing async_send=True")

    if findings:
        print("verify_email_delivery_surface: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_email_delivery_surface: EMAIL_DELIVERY_SURFACE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
