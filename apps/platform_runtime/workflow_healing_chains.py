"""Healing chain SOT — default fix chains for every registered workflow."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.workflow_fix_handlers import auto_fix_kind_is_executable
from apps.platform_runtime.workflow_recovery_playbook import recovery_strategy_for_workflow
from apps.platform_runtime.workflow_registry import WORKFLOWS, all_workflow_keys

# Explicit chain overrides (most-specific wins over module defaults).
_CHAIN_OVERRIDES: dict[str, list[str]] = {
    "tenant_school_provision": ["requeue_provision"],
    "tenant_school_create": ["requeue_provision"],
    "marketplace_webhook_deliver_due": ["replay_webhook"],
    "migration_bundle_apply": ["retry_failed_step"],
    "migration_bundle_advance": ["retry_failed_step"],
    "migration_bundle_fetch_assets": ["retry_failed_step"],
    "evals_bulk_grades": ["retry_failed_step"],
    "finance_auto_generate_fee_invoices": ["retry_failed_step"],
    "finance_auto_copy_fee_plans": ["retry_failed_step"],
    "orchestration_process_due": ["retry_failed_step"],
    "tenant_school_purge": ["retry_failed_step"],
    "tenant_school_offboard_purge": ["retry_failed_step"],
}

# Module-level defaults when no explicit override exists.
_MODULE_DEFAULT_CHAIN: dict[str, list[str]] = {
    "schools": ["resume_from_checkpoint"],
    "migration_cloud": ["retry_failed_step"],
    "siteconfig": ["retry_failed_step"],
    "finance": ["retry_failed_step"],
    "billing": ["retry_failed_step"],
    "reports": ["retry_failed_step"],
    "events": ["replay_webhook"],
    "marketplace": ["replay_webhook"],
    "orchestration": ["retry_failed_step"],
    "evals": ["retry_failed_step"],
    "ai": ["retry_once_with_backoff"],
    "platform_runtime": ["retry_failed_step"],
    "studio_os": ["retry_failed_step"],
    "accounts": ["retry_failed_step"],
    "people": ["retry_failed_step"],
    "portal": ["retry_failed_step"],
    "compliance": ["retry_failed_step"],
    "automation": ["retry_failed_step"],
    "communication": ["retry_failed_step"],
    "customersuccess": ["retry_failed_step"],
    "observability": ["retry_failed_step"],
    "payroll": ["retry_failed_step"],
    "assist_dock": ["retry_once_with_backoff"],
    "brand_experience": ["retry_failed_step"],
    "packages": ["retry_failed_step"],
    "registries": ["retry_failed_step"],
    "runtime_blueprints": ["retry_failed_step"],
    "schoolops": ["retry_failed_step"],
    "setup_studio": ["retry_failed_step"],
}

# Workflows that are visibility-only — no executable auto chain (operator detail).
_OPERATOR_GUIDED_ONLY: frozenset[str] = frozenset(
    {
        "workflow_progress_e2e_demo",
        "operator-tenant-lifecycle",
    }
)

_ASYNC_REQUEUE_KINDS: frozenset[str] = frozenset(
    {
        "requeue_provision",
        "retry_failed_step",
        "resume_from_checkpoint",
        "retry_once_with_backoff",
        "retry_after_rate_limit",
        "refresh_oauth_token_and_retry",
    }
)


def _dedupe_chain(chain: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in chain:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _executable_chain(chain: list[str]) -> list[str]:
    out: list[str] = []
    for kind in chain:
        if auto_fix_kind_is_executable(kind):
            out.append(kind)
    return out


def default_healing_chain_for_workflow(
    workflow_key: str,
    *,
    suggested_kind: str = "",
) -> list[str]:
    """Return the default executable healing chain for a workflow key."""

    key = str(workflow_key or "").strip()
    if not key or key in _OPERATOR_GUIDED_ONLY:
        return []

    if key in _CHAIN_OVERRIDES:
        return _executable_chain(_CHAIN_OVERRIDES[key])

    if suggested_kind and auto_fix_kind_is_executable(suggested_kind):
        return [suggested_kind]

    strategy = recovery_strategy_for_workflow(key)
    primary = str(strategy.get("primary_auto_fix_kind") or "").strip()
    if primary == "open_diagnostic_detail":
        primary = ""

    if primary == "resume_from_checkpoint" and key == "tenant_school_provision":
        primary = "requeue_provision"

    if primary and auto_fix_kind_is_executable(primary):
        return [primary]

    definition = WORKFLOWS.get(key)
    module = str(getattr(definition, "module", "") or strategy.get("module") or "").strip()
    module_chain = list(_MODULE_DEFAULT_CHAIN.get(module) or [])
    executable = _executable_chain(module_chain)
    if executable:
        return executable

    if primary:
        return [primary]

    definition = WORKFLOWS.get(key)
    if definition is not None and key not in _OPERATOR_GUIDED_ONLY:
        return ["retry_failed_step"]

    return []


def merge_operator_kind(*, chain: list[str], kind: str) -> list[str]:
    """Merge an operator-selected fix kind into a classified chain."""

    operator_kind = str(kind or "").strip()
    if operator_kind in ("", "apply_fix", "preview_fix"):
        return _dedupe_chain(chain)

    if operator_kind == "requeue_provision":
        merged = list(chain)
        if "requeue_provision" not in merged:
            merged.append("requeue_provision")
        return _dedupe_chain(merged)

    if operator_kind not in chain:
        return _dedupe_chain([operator_kind, *chain])
    return _dedupe_chain(chain)


def chain_indicates_async_job(chain: list[str]) -> bool:
    return any(step in _ASYNC_REQUEUE_KINDS for step in chain)


def healing_coverage_for_workflow(workflow_key: str) -> dict[str, Any]:
    """Audit row for one workflow key."""

    key = str(workflow_key or "").strip()
    strategy = recovery_strategy_for_workflow(key)
    chain = default_healing_chain_for_workflow(key)
    operator_only = key in _OPERATOR_GUIDED_ONLY
    covered = bool(chain) or operator_only or bool(strategy.get("covered"))
    return {
        "workflow_key": key,
        "chain": chain,
        "lane": strategy.get("lane", ""),
        "primary_auto_fix_kind": strategy.get("primary_auto_fix_kind", ""),
        "operator_guided_only": operator_only,
        "covered": covered,
    }


def healing_coverage_gaps() -> list[str]:
    """Workflow keys without an executable healing chain or explicit operator-only flag."""

    gaps: list[str] = []
    for key in all_workflow_keys():
        row = healing_coverage_for_workflow(key)
        if row["operator_guided_only"]:
            continue
        if not row["chain"]:
            gaps.append(key)
    return gaps


def healing_coverage_report() -> dict[str, Any]:
    rows = {key: healing_coverage_for_workflow(key) for key in all_workflow_keys()}
    gaps = healing_coverage_gaps()
    return {
        "workflow_count": len(rows),
        "covered_count": sum(1 for row in rows.values() if row.get("covered")),
        "gap_count": len(gaps),
        "gaps": gaps,
        "workflows": rows,
    }
