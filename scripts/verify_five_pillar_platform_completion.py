#!/usr/bin/env python3
"""
Five-pillar platform completion gate (AWS / Shopify / Salesforce / Linux / Google).

Mechanical audit that the CTO five-pillar prompt is 100% repo-contained. Writes
docs/generated/five_pillar_platform_audit.json on --write.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "five_pillar_platform_audit.json"


@dataclass
class Row:
    pillar: str
    check_id: str
    description: str
    status: str  # PASS | FAIL
    proof: str


def _exists(rel: str) -> bool:
    return (ROOT / rel).is_file()


def _contains(rel: str, needle: str) -> bool:
    path = ROOT / rel
    return path.is_file() and needle in path.read_text(encoding="utf-8")


def _run(
    cmd: list[str],
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = ((proc.stdout or "") + (proc.stderr or "")).strip()
        return proc.returncode, out[-400:] if out else ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 1, str(exc)


def _bola_test_count() -> int:
    path = ROOT / "apps/api/tests/test_bola_idor_matrix.py"
    if not path.is_file():
        return 0
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write JSON audit artifact.")
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run pillar Django test subset (slower).",
    )
    args = parser.parse_args()
    py = sys.executable
    rows: list[Row] = []

    def add(pillar: str, check_id: str, description: str, ok: bool, proof: str) -> None:
        rows.append(Row(pillar, check_id, description, "PASS" if ok else "FAIL", proof))

    # --- AWS ---
    add(
        "AWS",
        "cache_keys",
        "Versioned tenant resolution cache module",
        _exists("apps/schools/tenant_resolution_cache.py"),
        "tenant_resolution_cache.py",
    )
    add(
        "AWS",
        "cache_invalidation",
        "SchoolDomain/School signals invalidate cache",
        _exists("apps/schools/signals_tenant_cache.py")
        and _contains("apps/schools/apps.py", "signals_tenant_cache"),
        "signals_tenant_cache + apps.ready",
    )
    add(
        "AWS",
        "bola_me_schools",
        "me/schools uses schools_user_may_operate_on",
        _contains("apps/api/views_v1.py", "schools_user_may_operate_on"),
        "MeSchoolsView",
    )
    add(
        "AWS",
        "bola_me_schools_test",
        "HTTP test: foreign school absent from me/schools",
        _contains(
            "apps/api/tests/test_bola_idor_matrix.py",
            "test_me_schools_never_lists_foreign_school",
        )
        and _exists("apps/api/tests/test_me_schools_bola.py"),
        "test_bola_idor_matrix + test_me_schools_bola",
    )
    bola_n = _bola_test_count()
    add("AWS", "bola_matrix", "BOLA matrix >= 30 HTTP cases", bola_n >= 30, f"{bola_n} tests")

    code, tail = _run([py, "scripts/verify_tenant_resolution_cache_keys.py"])
    add("AWS", "cache_lint", "No legacy tenant:host cache keys", code == 0, tail or "ok")

    code, tail = _run([py, "scripts/verify_internal_tenant_slug_guards.py"])
    add(
        "AWS",
        "internal_tenant_slug_guards",
        "Internal ?tenant= APIs carry membership guards",
        code == 0,
        tail or "ok",
    )

    code, tail = _run([py, "scripts/verify_middleware_stack_order.py"])
    add("AWS", "middleware_order", "Middleware stack order gate", code == 0, tail or "ok")

    # --- Shopify ---
    add(
        "Shopify",
        "finance_ingress",
        "Finance webhook ingress boundary",
        _exists("apps/finance/webhook_ingress.py")
        and _contains("apps/finance/webhook_ingress.py", "resolve_webhook_dedup_bucket"),
        "apps/finance/webhook_ingress.py",
    )
    add(
        "Shopify",
        "payment_reexport",
        "payment app re-exports finance ingress",
        _exists("payment/webhook_ingress.py"),
        "payment/webhook_ingress.py",
    )
    add(
        "Shopify",
        "views_payments_wire",
        "views_payments uses resolve_webhook_dedup_bucket",
        _contains("apps/finance/views_payments.py", "resolve_webhook_dedup_bucket")
        and _contains("apps/finance/views_payments.py", "duplicate_webhook_response"),
        "views_payments.py",
    )
    add(
        "Shopify",
        "webhook_atomic_claim",
        "Webhook claim inside transaction.atomic",
        _exists("apps/finance/webhooks/claim.py")
        and _contains("apps/finance/views_payments.py", "claim_webhook_processing"),
        "webhooks/claim.py",
    )
    add(
        "Shopify",
        "payment_uniq_ext_ref",
        "Unique (invoice, external_reference) when ext ref set",
        _contains("apps/finance/models.py", "finance_payment_uniq_invoice_ext_ref"),
        "Payment.Meta.constraints",
    )
    add(
        "AWS",
        "tenant_api_guards",
        "school_id query param membership guard module",
        _exists("apps/schools/tenant_api_guards.py")
        and _contains("apps/api/analytics_viz_api.py", "user_may_access_school_api"),
        "tenant_api_guards.py",
    )

    # --- Salesforce ---
    add(
        "Salesforce",
        "event_dedup",
        "Domain event dispatch dedup + depth guard",
        _contains("apps/automation/domain_event_bridge.py", "_domain_event_already_dispatched")
        and _exists("apps/automation/workflow_limits.py"),
        "domain_event_bridge",
    )
    add(
        "Salesforce",
        "trigger_depth",
        "trigger_dispatcher honors workflow depth",
        _contains("apps/automation/trigger_dispatcher.py", "MAX_DOMAIN_EVENT_CHAIN_DEPTH"),
        "trigger_dispatcher.py",
    )
    add(
        "Salesforce",
        "notify_batch",
        "schoolops sweep uses notification batching",
        _contains("apps/schoolops/tasks.py", "enqueue_in_chunks"),
        "schoolops/tasks.py",
    )
    add(
        "Salesforce",
        "automation_bridge",
        "Automation app registers domain-event bridge",
        _contains("apps/automation/apps.py", "register_domain_event_trigger_subscriber"),
        "automation/apps.py",
    )
    add(
        "Salesforce",
        "outbox_school_prefetch",
        "Outbox batch prefetches schools for domain events",
        _contains("apps/events/tasks.py", "school_by_id"),
        "events/tasks.py",
    )

    # --- Linux ---
    add(
        "Linux",
        "extension_manifest",
        "Marketplace install validates extension manifest",
        _contains("apps/marketplace/lifecycle.py", "validate_marketplace_app_manifest"),
        "lifecycle.install_app",
    )
    add(
        "Linux",
        "extension_registry",
        "Extension registry sandbox validator",
        _contains("apps/marketplace/extension_registry.py", "validate_extension_manifest"),
        "extension_registry.py",
    )
    add(
        "Linux",
        "install_hook_delivery",
        "Install hooks dispatch via Celery/inline delivery",
        _exists("apps/marketplace/install_hook_delivery.py")
        and _contains("apps/marketplace/lifecycle.py", "dispatch_install_hooks"),
        "install_hook_delivery.py",
    )
    add(
        "Linux",
        "workflow_hook_registry",
        "Manifest workflow_hooks runtime registry",
        _exists("apps/marketplace/workflow_hook_registry.py")
        and _contains(
            "apps/automation/domain_event_bridge.py", "fire_manifest_workflow_hooks"
        ),
        "workflow_hook_registry.py",
    )
    add(
        "Linux",
        "governor_workflow_enforced",
        "Workflow governor limit enforced in run_workflow",
        _contains("apps/siteconfig/workflow_engine.py", "workflow_run_limit_exceeded"),
        "workflow_engine.run_workflow",
    )

    # --- Google ---
    add(
        "Google",
        "list_search",
        "Bounded list_search helper module",
        _exists("apps/siteconfig/list_search.py"),
        "list_search.py",
    )
    add(
        "Google",
        "student_fts",
        "StudentProfile search_index + student_search filter",
        _exists("apps/people/student_search.py")
        and _contains("apps/people/models.py", "search_index")
        and _contains("apps/people/views_backend.py", "filter_students_by_search"),
        "people/student_search",
    )
    add(
        "Google",
        "document_fts",
        "Portal document search_index + document_search filter",
        _exists("apps/portal/document_search.py")
        and _contains("apps/portal/views_documents.py", "filter_documents_by_search"),
        "portal/document_search",
    )
    add(
        "Google",
        "kb_search",
        "Portal KB uses bounded list_search",
        _contains("apps/portal/views_kb.py", "apply_bounded_icontains"),
        "views_kb.py",
    )
    add(
        "Google",
        "backfill_cmd",
        "backfill_search_indexes management command",
        _exists("apps/siteconfig/management/commands/backfill_search_indexes.py"),
        "backfill_search_indexes",
    )
    add(
        "Google",
        "migration_0051",
        "StudentProfile search_index migration",
        _exists("apps/people/migrations/0051_studentprofile_search_index.py"),
        "0051_studentprofile_search_index",
    )
    add(
        "Google",
        "search_index_gin",
        "PostgreSQL GIN index on student search_index",
        _exists("apps/people/migrations/0052_studentprofile_search_index_gin.py"),
        "0052_studentprofile_search_index_gin",
    )
    add(
        "Google",
        "global_search_fts_students",
        "Global search uses filter_students_by_search for students",
        _contains("apps/api/search_api.py", "filter_students_by_search"),
        "search_api.py",
    )
    add(
        "Google",
        "ai_invoke_pii_redact",
        "invoke_with_request redacts PII heuristics before gateway",
        _contains("services/ai_helpers.py", 'md["pii_redacted"]'),
        "ai_helpers.invoke_with_request",
    )
    add(
        "PROOF",
        "seed_command",
        "seed_five_pillar_proof management command",
        _exists("apps/platform_runtime/management/commands/seed_five_pillar_proof.py"),
        "seed_five_pillar_proof",
    )
    add(
        "Shopify",
        "migration_0063",
        "Payment invoice+ext_ref unique migration",
        _exists("apps/finance/migrations/0063_payment_uniq_invoice_ext_ref.py"),
        "0063_payment_uniq_invoice_ext_ref",
    )
    add(
        "Shopify",
        "migration_0064",
        "WebhookLog provider+bucket unique migration",
        _exists("apps/finance/migrations/0064_webhooklog_uniq_provider_bucket.py"),
        "0064_webhooklog_uniq_provider_bucket",
    )
    add(
        "Shopify",
        "webhook_concurrent_test",
        "Parallel webhook claim race test",
        _exists("apps/finance/tests/test_webhook_claim_concurrent.py")
        and _contains(
            "apps/finance/tests/test_webhook_claim_concurrent.py",
            "test_rapid_sequential_claims_single_row",
        ),
        "test_webhook_claim_concurrent",
    )
    add(
        "Shopify",
        "invoice_serializer_amount_str",
        "Invoice/Payment serializers use amount_str wire format",
        _contains("apps/api/serializers.py", "amount_str")
        and _exists("apps/api/tests/test_invoice_serializer_money_wire.py"),
        "InvoiceSerializer.to_representation",
    )
    add(
        "Shopify",
        "json_decimal_api",
        "Finance invoice summary uses amount_str wire format",
        _contains("apps/finance/api_views.py", "amount_str"),
        "InvoiceViewSet.summary",
    )
    add(
        "Shopify",
        "json_decimal_analytics_api",
        "Financial analytics API uses amount_str (no float money)",
        _contains("apps/finance/api_views.py", "FinancialAnalyticsAPI")
        and _contains("apps/finance/api_views.py", '"total_invoiced": amount_str'),
        "FinancialAnalyticsAPI.get",
    )
    add(
        "Shopify",
        "json_decimal_module_tests",
        "json_decimal unit tests present",
        _exists("apps/finance/tests/test_json_decimal.py"),
        "test_json_decimal.py",
    )

    code, tail = _run([py, "scripts/verify_list_search_adoption.py"])
    add("Google", "search_adoption_lint", "Hot list views use search helpers", code == 0, tail or "ok")

    if args.run_tests:
        test_env = {
            **os.environ,
            "DJANGO_TEST_DB_FILE": str(ROOT / ".django_test_dbs" / "pillar_quick.sqlite3"),
        }
        code, tail = _run(
            [
                py,
                "scripts/run_sqlite_memory_tests.py",
                "apps.schools.tests.test_tenant_resolution_cache",
                "apps.siteconfig.tests.test_list_search",
                "apps.siteconfig.tests.test_tenant_switch_security",
                "apps.people.tests.test_student_search",
                "apps.marketplace.tests.test_extension_manifest_validation",
                "apps.marketplace.tests.test_install_manifest_gate",
                "apps.automation.tests.test_domain_event_bridge_depth",
                "apps.automation.tests.test_domain_event_dedup",
                "apps.automation.tests.test_trigger_dispatcher_depth",
                "apps.schoolops.tests.test_notification_batch",
                "apps.finance.tests.test_webhook_ingress",
                "apps.finance.tests.test_webhook_claim",
                "apps.finance.tests.test_webhook_claim_concurrent",
                "apps.finance.tests.test_json_decimal",
                "apps.api.tests.test_invoice_serializer_money_wire",
                "apps.finance.tests.test_payment_invoice_ext_ref_unique",
                "apps.finance.tests.test_views_payments_dedup_bucket",
                "apps.api.tests.test_me_schools_bola",
                "apps.api.tests.test_analytics_viz_api",
                "apps.schools.tests.test_tenant_api_guards",
                "apps.marketplace.tests.test_workflow_hook_registry",
                "apps.platform_runtime.tests.test_governor_workflow_limit",
                "services.tests.test_ai_helpers_pii_redact",
                "apps.portal.tests.test_document_search",
                "payment.tests.test_webhook_ingress",
                "--verbosity=1",
            ],
            timeout=900,
            env=test_env,
        )
        add("PROOF", "django_tests", "Pillar Django test subset green", code == 0, tail or "ok")

    failed = [r for r in rows if r.status == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": "FIVE_PILLAR_PLATFORM_PASS" if not failed else "FIVE_PILLAR_PLATFORM_FAIL",
        "passed": sum(1 for r in rows if r.status == "PASS"),
        "failed": len(failed),
        "rows": [asdict(r) for r in rows],
    }

    if args.write:
        GENERATED.parent.mkdir(parents=True, exist_ok=True)
        GENERATED.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for row in failed:
        print(
            f"FAIL [{row.pillar}] {row.check_id}: {row.description} — {row.proof}",
            file=sys.stderr,
        )

    if failed:
        print(f"verify_five_pillar_platform_completion: {len(failed)} FAIL", file=sys.stderr)
        return 1

    print(f"verify_five_pillar_platform_completion: {payload['verdict']} ({payload['passed']} checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
