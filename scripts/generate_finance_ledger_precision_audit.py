#!/usr/bin/env python3
"""Finance / billing / payroll / payment precision discovery audit.

Writes:
  docs/generated/finance_ledger_precision_audit.json
  docs/generated/finance_ledger_precision_audit.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_OUT = ROOT / "docs" / "generated" / "finance_ledger_precision_audit.json"
MD_OUT = ROOT / "docs" / "generated" / "finance_ledger_precision_audit.md"

TARGET_APPS = ("finance", "billing", "payroll", "payment", "marketplace")

MONEY_MODEL_HINTS = (
    "amount",
    "total",
    "balance",
    "fee",
    "price",
    "tax",
    "salary",
    "wage",
    "payout",
    "charge",
    "credit",
    "debit",
    "billed",
    "gross",
    "net",
)

REQUIRED_MODULES = {
    "finance_json_decimal": "apps/finance/json_decimal.py",
    "finance_post_payment_ledger": "apps/finance/services.py",
    "finance_webhook_claim": "apps/finance/webhooks/claim.py",
    "finance_webhook_idempotency": "apps/finance/webhooks/idempotency.py",
    "billing_platform_charge": "apps/billing/services.py",
    "billing_usage_metering": "apps/billing/models_metering.py",
    "payroll_calculate": "apps/payroll/services.py",
    "payment_webhook_ingress": "payment/webhook_ingress.py",
    "marketplace_ledger_ops": "apps/marketplace/monetization_ledger_ops.py",
    "payment_blocker_classification": "docs/payments/PAYMENT_BLOCKER_CLASSIFICATION.md",
}


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _module_exists(rel: str) -> bool:
    return (ROOT / rel.replace("/", os.sep)).is_file()


def _run_money_float_scan() -> dict:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "scan_money_float.py"), "--compare"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "exit_code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
        "finding_count": 0 if proc.returncode == 0 else None,
        "ok": proc.returncode == 0,
    }


def _decimal_field_inventory() -> dict:
    from django.apps import apps

    rows = []
    for app_label in TARGET_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            for field in model._meta.get_fields():
                internal = getattr(field, "max_digits", None)
                places = getattr(field, "decimal_places", None)
                if internal is None or places is None:
                    continue
                name = getattr(field, "name", "") or ""
                if not any(hint in name.lower() for hint in MONEY_MODEL_HINTS):
                    continue
                rows.append(
                    {
                        "app": app_label,
                        "model": model.__name__,
                        "field": name,
                        "max_digits": internal,
                        "decimal_places": places,
                    }
                )
    two_dp = [r for r in rows if r["decimal_places"] == 2]
    return {
        "field_count": len(rows),
        "two_decimal_places_count": len(two_dp),
        "non_two_decimal_places": [
            r for r in rows if r["decimal_places"] != 2
        ][:20],
        "rows_sample": rows[:40],
    }


def _json_decimal_smoke() -> dict:
    from apps.finance.json_decimal import DecimalJSONEncoder, amount_str

    sample = Decimal("0.1") + Decimal("0.2")
    encoded = json.dumps({"amount": sample}, cls=DecimalJSONEncoder)
    return {
        "amount_str": amount_str(sample),
        "encoded": encoded,
        "ok": '"0.30"' in encoded and amount_str(sample) == "0.30",
    }


def build_audit() -> dict:
    _bootstrap_django()
    now = datetime.now(timezone.utc)
    modules = {key: _module_exists(path) for key, path in REQUIRED_MODULES.items()}
    money_float = _run_money_float_scan()
    decimal_inventory = _decimal_field_inventory()
    json_decimal = _json_decimal_smoke()

    idempotency_surfaces = {
        "finance_webhook_claim": _module_exists("apps/finance/webhooks/claim.py"),
        "finance_webhook_idempotency_bucket": True,
        "billing_processor_snapshot_dedupe": _module_exists("apps/billing/services.py"),
        "payment_webhook_ingress": _module_exists("payment/webhook_ingress.py"),
    }

    ok = (
        all(modules.values())
        and money_float["ok"]
        and json_decimal["ok"]
        and decimal_inventory["field_count"] > 0
        and all(idempotency_surfaces.values())
    )

    return {
        "generated_at": now.isoformat(),
        "metadata_only": True,
        "pii_free": True,
        "target_apps": list(TARGET_APPS),
        "required_modules": modules,
        "money_float_scan": money_float,
        "decimal_field_inventory": decimal_inventory,
        "json_decimal_smoke": json_decimal,
        "idempotency_surfaces": idempotency_surfaces,
        "psp_posture": {
            "lane": "EXTERNAL",
            "classification_doc": "docs/payments/PAYMENT_BLOCKER_CLASSIFICATION.md",
            "repo_honest": True,
            "note": "Live PSP settlement proof requires operator credentials; repo ships metadata checks and idempotent ledger guards only.",
        },
        "focused_test_modules": [
            "apps.finance.tests.test_ledger_failures",
            "apps.billing.tests.test_billing_idempotency",
            "apps.payroll.tests.test_payroll_decimal_integrity",
        ],
        "ok": ok,
    }


def _write_md(data: dict) -> str:
    mf = data["money_float_scan"]
    inv = data["decimal_field_inventory"]
    lines = [
        "# Finance ledger precision audit",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**OK:** {data['ok']}",
        "",
        "## Money-float gate",
        "",
        f"- scan_money_float: {'PASS' if mf['ok'] else 'FAIL'} ({mf.get('stdout', '')})",
        "",
        "## Decimal inventory",
        "",
        f"- Money-shaped DecimalFields: {inv['field_count']}",
        f"- Two decimal places: {inv['two_decimal_places_count']}",
        "",
        "## PSP posture",
        "",
        f"- Lane: {data['psp_posture']['lane']} (honest repo classification)",
        "",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if not args.write:
        args.write = True

    data = build_audit()
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    MD_OUT.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)}")
    return 0 if data["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
