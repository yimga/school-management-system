#!/usr/bin/env python3
"""
Lane 2 operator playbook runner — batches 1170, 1171, 1174.

Runs safe metadata health checks and reports evidence gaps. Never fabricates
verified_live or completed charge IDs. Optional --init-evidence copies templates
to canonical pending paths for operator fill-in after live money.

Usage:
  python scripts/run_lane2_operator_playbook.py --school=demo-school --batch=all
  python scripts/run_lane2_operator_playbook.py --school=demo-school --batch=1170 --init-evidence
  python scripts/run_lane2_operator_playbook.py --school=demo-school --batch=1171 --production-ping
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Canonical evidence filenames (operator fills after supervised txn — see SFDP §8.1)
EVIDENCE_TARGETS: dict[str, tuple[str, str]] = {
    "1170_phase1": (
        "var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.json",
        "var/evidence/geos-99/psp/stripe/phase1_platform_charge_evidence.template.json",
    ),
    "1170_phase2": (
        "var/evidence/geos-99/psp/stripe/phase2_connect_pilot_evidence.json",
        "var/evidence/geos-99/psp/stripe/phase2_connect_pilot_evidence.template.json",
    ),
    "1174_reconciliation": (
        "var/evidence/geos-99/psp/live_reconciliation_evidence.json",
        "var/evidence/geos-99/psp/live_reconciliation_evidence.template.json",
    ),
}

BATCH_1171_PROVIDERS: tuple[tuple[str, str], ...] = (
    ("stripe", "metadata"),
    ("paystack", "metadata"),
    ("flutterwave", "metadata"),
    ("mtn_momo", "metadata"),
    ("orange_momo", "metadata"),
)

BATCH_1171_PRODUCTION_PING: tuple[str, ...] = ("stripe", "paystack", "flutterwave")

BATCH_1170_PROVIDERS: tuple[tuple[str, str], ...] = (("stripe", "metadata"),)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _evidence_pending(path: Path) -> bool:
    if not path.is_file():
        return True
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return True
    status = str(data.get("evidence_status") or data.get("status") or "").lower()
    if status in {"pending_operator", "pending", "not_started"}:
        return True
    # Template placeholders left unfilled
    for val in data.values():
        if isinstance(val, str) and ("YYYY-MM-DD" in val or val.startswith("<")):
            return True
    return False


def _init_evidence(target_rel: str, template_rel: str) -> str:
    target = ROOT / target_rel
    template = ROOT / template_rel
    if not template.is_file():
        return f"missing template {template_rel}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        return f"exists (skipped): {target_rel}"
    payload = json.loads(template.read_text(encoding="utf-8"))
    payload["evidence_status"] = "pending_operator"
    payload["initialized_at"] = _utc_now()
    payload["notes"] = (
        str(payload.get("notes") or "")
        + " Fill redacted IDs after supervised live charge; never commit secrets."
    ).strip()
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return f"initialized: {target_rel}"


def _run_gateway_check(school: str, provider: str, mode: str) -> dict:
    cmd = [
        sys.executable,
        str(ROOT / "manage.py"),
        "check_payment_gateways",
        f"--school={school}",
        f"--provider={provider}",
        f"--mode={mode}",
        "--settings=config.settings",
    ]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    proc = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True, text=True)
    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    parsed: dict | list | None = None
    if stdout:
        try:
            parsed = json.loads(stdout)
        except json.JSONDecodeError:
            parsed = None
    return {
        "provider": provider,
        "mode": mode,
        "exit_code": proc.returncode,
        "result": parsed,
        "stderr_tail": stderr[-500:] if stderr else "",
    }


def _batch_1170(school: str, *, init_evidence: bool, production_ping: bool) -> dict:
    steps: list[str] = []
    if init_evidence:
        for key in ("1170_phase1", "1170_phase2"):
            target, template = EVIDENCE_TARGETS[key]
            steps.append(_init_evidence(target, template))

    evidence: dict[str, str] = {}
    pending: list[str] = []
    for key, (target_rel, _) in EVIDENCE_TARGETS.items():
        if not key.startswith("1170"):
            continue
        path = ROOT / target_rel
        evidence[key] = target_rel
        if _evidence_pending(path):
            pending.append(target_rel)

    checks: list[dict] = []
    for provider, mode in BATCH_1170_PROVIDERS:
        checks.append(_run_gateway_check(school, provider, mode))
    if production_ping:
        checks.append(_run_gateway_check(school, "stripe", "production_ping"))

    return {
        "batch": "1170",
        "title": "Stripe live PSP + Connect pilot evidence",
        "evidence_paths": evidence,
        "evidence_pending": pending,
        "gateway_checks": checks,
        "init_steps": steps,
        "operator_next": [
            "Stripe Dashboard: select non-recurring + recurring + platform/marketplace",
            "Render: STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_WEBHOOK_SECRET",
            "Webhook: /finance/payments/webhook/stripe/",
            "One supervised platform charge + refund; file phase1_platform_charge_evidence.json",
            "Connect Express pilot at /siteconfig/billing-stripe/; file phase2_connect_pilot_evidence.json",
            "Flip stripe_global_cards / stripe_connect_platform in external_dependencies_register.json",
        ],
    }


def _batch_1171(school: str, *, production_ping: bool) -> dict:
    checks: list[dict] = []
    for provider, mode in BATCH_1171_PROVIDERS:
        checks.append(_run_gateway_check(school, provider, mode))
    if production_ping:
        for provider in BATCH_1171_PRODUCTION_PING:
            checks.append(_run_gateway_check(school, provider, "production_ping"))

    return {
        "batch": "1171",
        "title": "WAfrica + global PSP keys per tenant",
        "gateway_checks": checks,
        "operator_next": [
            "Enable Integration(provider=payments) per PSP on pilot tenant (Django admin / School Studio)",
            "Run metadata first: python manage.py check_payment_gateways --school=<slug> --provider=<psp> --mode=metadata",
            "When sk_live_* exists: re-run with --mode=production_ping (Stripe/Paystack/Flutterwave only)",
            "Supervised live charge per corridor; copy template → var/evidence/geos-99/psp/<psp>/phase1_*_evidence.json",
            "Flip child register row to verified_live only after evidence on disk",
        ],
    }


def _batch_1174(school: str, *, init_evidence: bool) -> dict:
    steps: list[str] = []
    target_rel, template_rel = EVIDENCE_TARGETS["1174_reconciliation"]
    if init_evidence:
        steps.append(_init_evidence(target_rel, template_rel))

    path = ROOT / target_rel
    pending = [target_rel] if _evidence_pending(path) else []

    # Rollup metadata for all rails (health snapshots written by command)
    checks: list[dict] = []
    checks.append(_run_gateway_check(school, "", "metadata"))

    return {
        "batch": "1174",
        "title": "Live payment + receipt reconciliation evidence",
        "evidence_path": target_rel,
        "evidence_pending": pending,
        "gateway_checks": checks,
        "init_steps": steps,
        "operator_next": [
            "After supervised live charge: capture PaymentGatewayHealthSnapshot from check_payment_gateways",
            "Record ledger entry IDs + webhook delivery IDs (redacted) in live_reconciliation_evidence.json",
            "Attach settlement artifact reference (Stripe payout export path, Paystack settlement CSV, etc.)",
            "Do not store secrets or full PAN in evidence JSON",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Lane 2 operator playbook (1170/1171/1174)")
    parser.add_argument("--school", required=True, help="Tenant school slug")
    parser.add_argument(
        "--batch",
        default="all",
        choices=("1170", "1171", "1174", "all"),
        help="Which SOT batch playbook to run",
    )
    parser.add_argument(
        "--init-evidence",
        action="store_true",
        help="Copy evidence templates to canonical pending JSON paths (no secrets)",
    )
    parser.add_argument(
        "--production-ping",
        action="store_true",
        help="Include production_ping where supported (requires live keys in env/Integration)",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write docs/generated/lane2_operator_preflight.json",
    )
    args = parser.parse_args()

    report: dict = {
        "generated_at": _utc_now(),
        "school_slug": args.school,
        "batches": [],
        "scaffold_verifiers": {},
    }

    # Repo scaffold gates (must pass before operator work)
    for script, token in (
        ("verify_payment_gateway_lane2_scaffold.py", "PAYMENT_GATEWAY_LANE2_SCAFFOLD_PASS"),
        ("verify_stripe_platform_settlement_scaffold.py", "STRIPE_PLATFORM_SETTLEMENT_SCAFFOLD_PASS"),
        ("verify_geos_lane2_scaffold.py", "GEOS_LANE2_SCAFFOLD_PASS"),
    ):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        report["scaffold_verifiers"][script] = {
            "exit_code": proc.returncode,
            "pass": token in (proc.stdout or ""),
        }
        if proc.returncode != 0:
            print(f"run_lane2_operator_playbook: FAIL — {script}", file=sys.stderr)
            print(proc.stderr or proc.stdout, file=sys.stderr)
            return 1

    batches = ("1170", "1171", "1174") if args.batch == "all" else (args.batch,)
    all_pending: list[str] = []

    for batch in batches:
        if batch == "1170":
            block = _batch_1170(
                args.school,
                init_evidence=args.init_evidence,
                production_ping=args.production_ping,
            )
        elif batch == "1171":
            block = _batch_1171(args.school, production_ping=args.production_ping)
        else:
            block = _batch_1174(args.school, init_evidence=args.init_evidence)
        report["batches"].append(block)
        all_pending.extend(block.get("evidence_pending") or [])

    report["evidence_pending_all"] = sorted(set(all_pending))
    report["lane2_money_status"] = (
        "pending_operator_evidence" if all_pending else "evidence_files_present_review_required"
    )

    if args.write_report:
        out = ROOT / "docs" / "generated" / "lane2_operator_preflight.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out.relative_to(ROOT)}")

    print(json.dumps(report, indent=2))

    if all_pending:
        print(
            "run_lane2_operator_playbook: LANE2_PENDING_OPERATOR_EVIDENCE — "
            + ", ".join(all_pending),
            file=sys.stderr,
        )
        return 2
    print("run_lane2_operator_playbook: LANE2_EVIDENCE_PATHS_PRESENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
