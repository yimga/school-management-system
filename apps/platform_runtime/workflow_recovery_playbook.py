"""Recovery strategy coverage for every registered platform workflow."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.workflow_registry import WORKFLOWS


_STRATEGY_BY_MODULE: dict[str, dict[str, Any]] = {
    "schools": {
        "lane": "provisioning_resume",
        "auto_fix_kind": "resume_from_checkpoint",
        "summary": "Resume school provisioning from the last safe checkpoint.",
    },
    "migration_cloud": {
        "lane": "migration_checkpoint",
        "auto_fix_kind": "retry_failed_step",
        "summary": "Retry the failed migration checkpoint after dependency checks.",
    },
    "siteconfig": {
        "lane": "tenant_config_retry",
        "auto_fix_kind": "retry_failed_step",
        "summary": "Retry tenant configuration writes with audit context attached.",
    },
    "finance": {
        "lane": "financial_reconciliation",
        "auto_fix_kind": "retry_failed_step",
        "summary": "Reconcile financial state before retrying the failed step.",
    },
    "billing": {
        "lane": "financial_reconciliation",
        "auto_fix_kind": "retry_failed_step",
        "summary": "Reconcile billing state before retrying the failed step.",
    },
    "reports": {
        "lane": "report_regeneration",
        "auto_fix_kind": "retry_failed_step",
        "summary": "Regenerate the report artifact from canonical source data.",
    },
    "events": {
        "lane": "event_replay",
        "auto_fix_kind": "replay_webhook",
        "summary": "Replay the event or webhook delivery identified by the run payload.",
    },
    "ai": {
        "lane": "ai_retry",
        "auto_fix_kind": "retry_once_with_backoff",
        "summary": "Retry the AI-assisted step with backoff and operator context.",
    },
}


def recovery_strategy_for_workflow(workflow_key: str) -> dict[str, Any]:
    """Return the declared recovery lane for a registry workflow key."""

    key = str(workflow_key or "").strip()
    definition = WORKFLOWS.get(key)
    if key == "tenant_school_provision":
        return {
            "workflow_key": key,
            "lane": "provisioning_resume",
            "auto_fix_kind": "resume_from_checkpoint",
            "primary_auto_fix_kind": "resume_from_checkpoint",
            "summary": "Requeue provisioning through the idempotent school setup task.",
            "covered": True,
        }
    if definition is None:
        return {
            "workflow_key": key,
            "lane": "operator_guided",
            "auto_fix_kind": "open_diagnostic_detail",
            "primary_auto_fix_kind": "open_diagnostic_detail",
            "summary": "Open run detail for traceback, payload, and copilot recovery context.",
            "covered": bool(key),
        }
    module = str(definition.module or "").strip()
    strategy = dict(_STRATEGY_BY_MODULE.get(module) or {})
    if not strategy:
        strategy = {
            "lane": "operator_guided",
            "auto_fix_kind": "open_diagnostic_detail",
            "summary": "Open run detail for traceback, payload, and copilot recovery context.",
        }
    strategy.update(
        {
            "workflow_key": key,
            "primary_auto_fix_kind": strategy.get("auto_fix_kind", ""),
            "workflow_title": definition.title,
            "module": module,
            "owner_team": getattr(definition, "owner_team", "") or "",
            "covered": True,
        }
    )
    return strategy


def workflow_recovery_coverage() -> dict[str, dict[str, Any]]:
    """Return recovery strategy metadata for all registered workflows."""

    return {
        key: recovery_strategy_for_workflow(key)
        for key in sorted(WORKFLOWS)
    }


def recovery_coverage_gaps() -> list[str]:
    """Registered workflow keys without any recovery strategy."""

    return [
        key
        for key, strategy in workflow_recovery_coverage().items()
        if not strategy.get("covered")
    ]
