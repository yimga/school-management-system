#!/usr/bin/env python3
"""
Ecosystem Sovereignty & Category-Defining Validation Matrix (gatekeeper orchestrator).

Produces docs/generated/ecosystem_sovereignty_validation_matrix.json with the
prompt-mandated four sections:
  1. architectural_limitation_log
  2. system_sovereignty_rewrite (production module map — not placeholders)
  3. adversarial_sweep_2
  4. sot_platform_variables

Runs child pillar verifiers and fails CI when repo-mechanical proof is not green.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "ecosystem_sovereignty_validation_matrix.json"
VECTORS = ROOT / "docs" / "generated" / "tenant_sovereignty_platform_vectors.json"
FIVE_PILLAR_JSON = ROOT / "docs" / "generated" / "five_pillar_platform_audit.json"


def _run(cmd: list[str], *, timeout: int = 1200) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out[-500:] if out else ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def _load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _limitation_log() -> list[dict]:
    """Honest engineering limits — repo vs live/ecosystem."""
    return [
        {
            "id": "LIVE_PSP_SETTLEMENT",
            "pillar": "Shopify",
            "severity": "external_blocker",
            "finding": (
                "No production PSP corridor with a settled live transaction is evidenced "
                "in-repo; ledger math and webhook idempotency are proven mechanically only."
            ),
            "remediation_owner": "operator",
            "sot": "docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md §2",
        },
        {
            "id": "LIVE_SOC2",
            "pillar": "AWS",
            "severity": "external_blocker",
            "finding": "SOC 2 / ISO attestation claims require auditor sign-off outside the repo.",
            "remediation_owner": "counsel + auditor",
            "sot": "docs/compliance/SOC2_PCI_AUDITOR_ENGAGEMENT_GUIDE.md",
        },
        {
            "id": "LIVE_THIRD_PARTY_APPS",
            "pillar": "Linux",
            "severity": "external_blocker",
            "finding": (
                "Marketplace extension surface is repo-complete; zero external publisher "
                "apps in production catalog."
            ),
            "remediation_owner": "partner ecosystem",
            "sot": "docs/developer/PARTNER_APP_CERTIFICATION.md",
        },
        {
            "id": "SEARCH_OPENSEARCH_DEFAULT",
            "pillar": "Google",
            "severity": "deferred",
            "finding": (
                "Student/document search uses bounded helpers + PostgreSQL GIN on "
                "search_index; hosted OpenSearch cluster is not the default backend."
            ),
            "remediation_owner": "platform",
            "proof_in_repo": "apps/people/migrations/0052_studentprofile_search_index_gin.py",
        },
        {
            "id": "PERF_ZERO_TICKET_STRICT",
            "pillar": "Salesforce",
            "severity": "flake_under_strict",
            "finding": (
                "Forensic PERF_BUDGET_STRICT smoke on zero-ticket permissions may fail "
                "on cold SQLite dev DBs (RuntimeDefaults query churn); warn-only unless "
                "PERF_BUDGET_STRICT=1 in CI."
            ),
            "remediation_owner": "platform",
            "proof_in_repo": "scripts/check_performance_budgets.py",
        },
        {
            "id": "SQLITE_TEST_PARALLELISM",
            "pillar": "AWS",
            "severity": "environment",
            "finding": (
                "Parallel webhook claim stress tests are sequential on SQLite CI; "
                "Postgres production uses DB unique constraint + select_for_update."
            ),
            "remediation_owner": "platform",
            "proof_in_repo": "apps/finance/tests/test_webhook_claim_concurrent.py",
        },
    ]


def _sovereignty_rewrite() -> dict:
    """Production module map per pillar (implemented — not placeholders)."""
    return {
        "foundational_layer_first": "TENANT_SOVEREIGNTY",
        "pillars": {
            "Linux": {
                "extension_manifest_validation": "apps/marketplace/extension_registry.py",
                "install_lifecycle": "apps/marketplace/lifecycle.py",
                "install_hook_delivery": "apps/marketplace/install_hook_delivery.py",
                "workflow_hook_registry": "apps/marketplace/workflow_hook_registry.py",
                "workflow_governor": "apps/platform_runtime/governor_limits.py",
                "workflow_enforcement": "apps/siteconfig/workflow_engine.py",
                "domain_event_bridge": "apps/automation/domain_event_bridge.py",
            },
            "AWS": {
                "tenant_resolution_cache": "apps/schools/tenant_resolution_cache.py",
                "cache_invalidation": "apps/schools/signals_tenant_cache.py",
                "tenant_api_guards": "apps/schools/tenant_api_guards.py",
                "bola_matrix_tests": "apps/api/tests/test_bola_idor_matrix.py",
                "middleware_order_gate": "scripts/verify_middleware_stack_order.py",
                "tenant_isolation_scanner": "scripts/scan_tenant_queryset_safety.py",
            },
            "Shopify": {
                "webhook_ingress": "apps/finance/webhook_ingress.py",
                "atomic_claim": "apps/finance/webhooks/claim.py",
                "payment_unique_ext_ref": "apps/finance/migrations/0063_payment_uniq_invoice_ext_ref.py",
                "webhook_unique_bucket": "apps/finance/migrations/0064_webhooklog_uniq_provider_bucket.py",
                "json_decimal_wire": "apps/finance/json_decimal.py",
                "wallet_pessimistic_lock": "apps/finance/services.py::pay_invoice_with_wallet",
                "api_serializers_amount_str": "apps/api/serializers.py",
                "financial_analytics_api": "apps/finance/api_views.py::FinancialAnalyticsAPI",
            },
            "Salesforce": {
                "domain_event_dedup": "apps/automation/domain_event_bridge.py",
                "workflow_depth": "apps/automation/trigger_dispatcher.py",
                "outbox_prefetch": "apps/events/tasks.py",
                "notification_batching": "apps/schoolops/tasks.py",
            },
            "Google": {
                "list_search": "apps/siteconfig/list_search.py",
                "student_search": "apps/people/student_search.py",
                "document_search": "apps/portal/document_search.py",
                "global_search_api": "apps/api/search_api.py",
                "gin_migration": "apps/people/migrations/0052_studentprofile_search_index_gin.py",
                "search_backfill": "apps/siteconfig/management/commands/backfill_search_indexes.py",
                "ai_pii_redact": "services/ai_helpers.py::invoke_with_request",
            },
        },
    }


def _sot_platform_variables() -> dict:
    base = _load_json(VECTORS)
    return {
        "schema_version": "2.0.0",
        "matrix": "ecosystem_sovereignty_category_defining",
        "tenant_sovereignty": base.get("tenant_sovereignty", {}),
        "cross_pillar_env": {
            **base.get("cross_pillar_env", {}),
            "SEND_FINANCE_SIGNALS": "django.settings (default True; tests set False)",
            "MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND": "os.environ MIGRATION_CLOUD_AUDIT_SIGNING_BACKEND",
            "OBSERVABILITY_METRICS_BACKEND": "os.environ OBSERVABILITY_METRICS_BACKEND",
            "DJANGO_TEST_DB_FILE": "scripts/run_sqlite_memory_tests.py pillar subset",
        },
        "finance_precision": {
            "wire_format": "amount_str / DecimalJSONEncoder",
            "module": "apps/finance/json_decimal.py",
            "unique_constraints": [
                "finance_payment_uniq_invoice_ext_ref",
                "finance_webhooklog_uniq_provider_bucket",
            ],
        },
        "seed_commands": [
            "seed_five_pillar_proof",
            "backfill_search_indexes",
        ],
        "ci_gates": [
            "scripts/verify_ecosystem_sovereignty_matrix.py",
            "scripts/verify_five_pillar_platform_completion.py",
            "scripts/verify_tenant_sovereignty_pillar.py",
            "scripts/verify_six_pillar_global_dominance.py",
        ],
        "honest_external_blockers": base.get("honest_external_blockers", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write JSON matrix artifact.")
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run five-pillar Django proof subset (slow).",
    )
    parser.add_argument(
        "--skip-child-verifiers",
        action="store_true",
        help="Only assemble matrix from existing generated JSON (no subprocess).",
    )
    args = parser.parse_args()
    py = sys.executable

    child_results: list[dict] = []
    if not args.skip_child_verifiers:
        five_cmd = [py, "scripts/verify_five_pillar_platform_completion.py", "--write"]
        if args.run_tests:
            five_cmd.append("--run-tests")
        code, tail = _run(five_cmd, timeout=1200)
        child_results.append(
            {
                "gate": "verify_five_pillar_platform_completion",
                "exit_code": code,
                "proof": tail,
            }
        )

        for script, timeout in (
            ("verify_tenant_sovereignty_pillar.py", 300),
            ("verify_ai_engine_room.py", 300),
            ("verify_internal_tenant_slug_guards.py", 120),
        ):
            code, tail = _run([py, f"scripts/{script}"], timeout=timeout)
            child_results.append(
                {"gate": script.replace(".py", ""), "exit_code": code, "proof": tail}
            )

    five_audit = _load_json(FIVE_PILLAR_JSON)
    five_verdict = five_audit.get("verdict", "UNKNOWN")
    child_fail = [c for c in child_results if c.get("exit_code", 1) != 0]

    adversarial = {
        "sweep_id": "adversarial_sweep_2",
        "bola_http_cases": five_audit.get("rows", []),
        "bola_matrix_count": next(
            (
                r.get("proof")
                for r in five_audit.get("rows", [])
                if r.get("check_id") == "bola_matrix"
            ),
            "see test_bola_idor_matrix.py",
        ),
        "revalidation_gates": [
            {
                "name": "internal_tenant_slug_guards",
                "module": "scripts/verify_internal_tenant_slug_guards.py",
            },
            {
                "name": "webhook_claim_race_safety",
                "module": "apps/finance/tests/test_webhook_claim_concurrent.py",
            },
            {
                "name": "payment_ext_ref_unique",
                "module": "apps/finance/tests/test_payment_invoice_ext_ref_unique.py",
            },
            {
                "name": "invoice_serializer_money_wire",
                "module": "apps/api/tests/test_invoice_serializer_money_wire.py",
            },
            {
                "name": "ai_helpers_pii_redact",
                "module": "services/tests/test_ai_helpers_pii_redact.py",
            },
        ],
        "child_verifier_results": child_results,
        "tightening_notes": [
            "Webhook claim uses select_for_update + partial unique (provider, idempotency_bucket).",
            "Payment duplicate external_reference rejected at DB + full_clean.",
            "Internal ?tenant= APIs require schools_user_may_operate_on membership.",
        ],
    }

    repo_mechanical_pass = (
        five_verdict == "FIVE_PILLAR_PLATFORM_PASS" and not child_fail
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": (
            "ECOSYSTEM_SOVEREIGNTY_MATRIX_PASS"
            if repo_mechanical_pass
            else "ECOSYSTEM_SOVEREIGNTY_MATRIX_FAIL"
        ),
        "repo_mechanical_complete": repo_mechanical_pass,
        "live_ecosystem_complete": False,
        "live_ecosystem_note": (
            "Repo proves architecture; live PSP/SOC2/pilots remain BLOCKED_EXTERNAL "
            "per docs/RUNMYCAMPUS_FIVE_PILLAR_CERTIFICATION.md"
        ),
        "foundational_layer_pressure_tested_first": "TENANT_SOVEREIGNTY",
        "1_architectural_limitation_log": _limitation_log(),
        "2_system_sovereignty_rewrite": _sovereignty_rewrite(),
        "3_adversarial_sweep_2": adversarial,
        "4_sot_platform_variables": _sot_platform_variables(),
        "five_pillar_verdict": five_verdict,
        "five_pillar_passed": five_audit.get("passed"),
        "five_pillar_failed": five_audit.get("failed"),
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if not repo_mechanical_pass:
        print(
            f"verify_ecosystem_sovereignty_matrix: {payload['verdict']} "
            f"(five_pillar={five_verdict}, child_fails={len(child_fail)})",
            file=sys.stderr,
        )
        return 1

    print(
        f"verify_ecosystem_sovereignty_matrix: {payload['verdict']} "
        f"(five_pillar={five_verdict}, foundational_layer=TENANT_SOVEREIGNTY)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
