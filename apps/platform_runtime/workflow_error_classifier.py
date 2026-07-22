"""Rule-based error fingerprinting for workflow self-healing (all workflows)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from apps.platform_runtime.workflow_healing_chains import default_healing_chain_for_workflow
from apps.platform_runtime.workflow_recovery_playbook import recovery_strategy_for_workflow


@dataclass
class ErrorFingerprint:
    class_key: str
    human_title: str
    human_cause: str
    human_fix_summary: str
    recommended_chain: list[str] = field(default_factory=list)
    confidence: str = "medium"
    requires_network: bool = False
    safe_for_autopilot: bool = False
    diagnosis_source: str = "rule_based"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _error_text(run: Any) -> str:
    parts: list[str] = []
    err = getattr(run, "error_summary", None) or {}
    if isinstance(err, dict):
        for key in ("message", "detail", "type", "code"):
            val = err.get(key)
            if val:
                parts.append(str(val))
    payload = getattr(run, "payload_summary", None) or {}
    if isinstance(payload, dict):
        for key in ("last_error", "error", "failure_reason"):
            val = payload.get(key)
            if val:
                parts.append(str(val))
    remediation = getattr(run, "suggested_remediation", None) or {}
    if isinstance(remediation, dict) and remediation.get("human_action"):
        parts.append(str(remediation["human_action"]))
    return " ".join(parts).lower()


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


def _cross_cutting_preflight(text: str, chain: list[str]) -> list[str]:
    """Prepend universal repair steps when error text matches."""

    out = list(chain)
    if (
        "upstream worker did not respond" in text
        or "heartbeat" in text
        or "abandoned" in text
        or "no heartbeat" in text
        or "kombuoperationalerror" in text
        or "brokernotavailable" in text
    ):
        if "clear_stale_lock" not in out:
            out.insert(0, "clear_stale_lock")
    if re.search(r"httperror.*429|rate limit|too many requests", text):
        if "retry_after_rate_limit" not in out:
            out.insert(0, "retry_after_rate_limit")
    if re.search(
        r"connectionerror|timeout|readtimeout|connecttimeout|httperror.*5\d\d",
        text,
    ):
        # Provision requeue already retries the job — do not prepend a no-op
        # retry_once_with_backoff that only stamps metadata.
        if (
            "retry_once_with_backoff" not in out
            and "retry_failed_step" not in out
            and "requeue_provision" not in out
        ):
            out.insert(0, "retry_once_with_backoff")
    if re.search(r"invalid_grant|token.*expired|expired.*token", text):
        if "refresh_oauth_token_and_retry" not in out:
            out.insert(0, "refresh_oauth_token_and_retry")
    return _dedupe_chain(out)


def _strategy_fingerprint(
    *,
    workflow_key: str,
    text: str,
    run: Any,
    class_key: str,
    title: str,
    cause: str,
    fix_summary: str,
    chain: list[str],
    confidence: str = "medium",
    requires_network: bool = False,
    safe_for_autopilot: bool = False,
) -> ErrorFingerprint:
    remediation = getattr(run, "suggested_remediation", None) or {}
    suggested_kind = str(remediation.get("auto_fix_kind") or "").strip()
    if suggested_kind and suggested_kind not in chain:
        chain = _dedupe_chain([suggested_kind, *chain])
    if not chain:
        chain = default_healing_chain_for_workflow(
            workflow_key,
            suggested_kind=suggested_kind,
        )
    chain = _cross_cutting_preflight(text, chain)
    strategy = recovery_strategy_for_workflow(workflow_key)
    return ErrorFingerprint(
        class_key=class_key,
        human_title=title or str(strategy.get("workflow_title") or workflow_key.replace("_", " ").title()),
        human_cause=cause or str(remediation.get("human_action") or strategy.get("summary") or ""),
        human_fix_summary=fix_summary or str(strategy.get("summary") or "Apply the recommended fix chain."),
        recommended_chain=chain,
        confidence=confidence,
        requires_network=requires_network,
        safe_for_autopilot=safe_for_autopilot,
    )


def _classify_provision(run: Any, text: str) -> ErrorFingerprint:
    workflow_key = "tenant_school_provision"

    if "already exists" in text and "relation" in text:
        return _strategy_fingerprint(
            workflow_key=workflow_key,
            text=text,
            run=run,
            class_key="duplicate_relation",
            title="Partial schema from a prior run",
            cause=(
                "A database table from school setup already exists, usually from "
                "a previous provisioning attempt that stopped mid-migration."
            ),
            fix_summary="Repair tenant schema drift, then re-queue provisioning.",
            chain=["repair_tenant_schema_drift", "requeue_provision"],
            confidence="high",
            requires_network=True,
            safe_for_autopilot=True,
        )

    if "duplicate key value violates unique constraint" in text:
        return _strategy_fingerprint(
            workflow_key=workflow_key,
            text=text,
            run=run,
            class_key="idempotency_collision",
            title="Duplicate record collision",
            cause="Provisioning retried into a row that already exists.",
            fix_summary="Clear stale locks if present, then re-queue provisioning.",
            chain=["clear_stale_lock", "requeue_provision"],
            confidence="medium",
            requires_network=True,
        )

    if "can't create tenant outside the public schema" in text or (
        "public schema" in text and "tenant" in text
    ):
        return _strategy_fingerprint(
            workflow_key=workflow_key,
            text=text,
            run=run,
            class_key="schema_context_violation",
            title="Tenant schema context mismatch",
            cause="Migration ran outside the correct tenant schema context.",
            fix_summary="Run tenant migrations, then re-queue provisioning.",
            chain=["run_tenant_migrations", "requeue_provision"],
        )

    if re.search(r"relation .+ does not exist", text):
        return _strategy_fingerprint(
            workflow_key=workflow_key,
            text=text,
            run=run,
            class_key="missing_relation",
            title="Missing database objects",
            cause="Expected tables or relations are not present in the tenant schema.",
            fix_summary="Run tenant migrations, then re-queue provisioning.",
            chain=["run_tenant_migrations", "requeue_provision"],
        )

    if (
        "upstream worker did not respond" in text
        or "heartbeat" in text
        or "abandoned" in text
        or "no heartbeat" in text
    ):
        return _strategy_fingerprint(
            workflow_key=workflow_key,
            text=text,
            run=run,
            class_key="worker_timeout",
            title="Worker timed out",
            cause=(
                "The background worker stopped sending heartbeats before "
                "provisioning finished."
            ),
            fix_summary="Clear stale locks if present, then re-queue provisioning.",
            chain=["clear_stale_lock", "requeue_provision"],
            confidence="high",
            requires_network=True,
            safe_for_autopilot=True,
        )

    step = str(getattr(run, "current_step_name", "") or "").strip()
    if step == "tenant_schema":
        return _strategy_fingerprint(
            workflow_key=workflow_key,
            text=text,
            run=run,
            class_key="tenant_schema_stalled",
            title="Tenant schema step stalled",
            cause=(
                "Campus workspace setup did not finish creating or migrating the "
                "tenant database schema."
            ),
            fix_summary=(
                "Repair tenant schema drift, then re-queue idempotent provisioning."
            ),
            chain=[
                "cancel_duplicate_run",
                "repair_tenant_schema_drift",
                "requeue_provision",
            ],
            confidence="high",
            requires_network=True,
            safe_for_autopilot=True,
        )

    return _strategy_fingerprint(
        workflow_key=workflow_key,
        text=text,
        run=run,
        class_key="generic_provision_failure",
        title="Provisioning failed",
        cause=(
            "School setup did not complete. Re-queue is idempotent and resumes "
            "from the last safe checkpoint."
        ),
        fix_summary="Re-queue the idempotent provisioning task.",
        chain=["requeue_provision"],
        confidence="medium",
        requires_network=True,
        safe_for_autopilot=True,
    )


def _classify_migration(run: Any, text: str, workflow_key: str) -> ErrorFingerprint:
    chain = default_healing_chain_for_workflow(workflow_key)
    if re.search(r"webhook|delivery|signature", text):
        chain = _dedupe_chain(["replay_webhook", *chain])
    return _strategy_fingerprint(
        workflow_key=workflow_key,
        text=text,
        run=run,
        class_key="migration_failure",
        title="Migration workflow failed",
        cause="A migration bundle step failed before completion.",
        fix_summary="Retry the failed migration checkpoint after dependency checks.",
        chain=chain or ["retry_failed_step"],
        requires_network=True,
    )


def _classify_webhook(run: Any, text: str, workflow_key: str) -> ErrorFingerprint:
    return _strategy_fingerprint(
        workflow_key=workflow_key,
        text=text,
        run=run,
        class_key="webhook_delivery_failure",
        title="Webhook delivery failed",
        cause="The webhook delivery did not succeed or the upstream rejected the payload.",
        fix_summary="Replay the webhook delivery after verifying the subscription secret.",
        chain=["replay_webhook"],
        confidence="high",
        requires_network=True,
        safe_for_autopilot=True,
    )


def _classify_finance(run: Any, text: str, workflow_key: str) -> ErrorFingerprint:
    return _strategy_fingerprint(
        workflow_key=workflow_key,
        text=text,
        run=run,
        class_key="finance_automation_failure",
        title="Finance automation failed",
        cause="A scheduled finance workflow failed before writing its automation log.",
        fix_summary="Retry the failed finance step after reconciling tenant billing state.",
        chain=default_healing_chain_for_workflow(workflow_key) or ["retry_failed_step"],
        requires_network=False,
    )


def classify_workflow_run(run: Any) -> ErrorFingerprint:
    """Map any failed/stuck run to a fix chain using rules + recovery playbook."""

    workflow_key = str(getattr(run, "workflow_key", "") or "")
    text = _error_text(run)

    if workflow_key == "tenant_school_provision":
        return _classify_provision(run, text)

    if workflow_key.startswith("migration_bundle"):
        return _classify_migration(run, text, workflow_key)

    if workflow_key in ("marketplace_webhook_deliver_due",) or "webhook" in workflow_key:
        return _classify_webhook(run, text, workflow_key)

    if workflow_key.startswith("finance_auto_"):
        return _classify_finance(run, text, workflow_key)

    strategy = recovery_strategy_for_workflow(workflow_key)
    lane = str(strategy.get("lane") or "")
    if lane == "event_replay":
        return _classify_webhook(run, text, workflow_key)

    remediation = getattr(run, "suggested_remediation", None) or {}
    suggested_kind = str(remediation.get("auto_fix_kind") or "").strip()
    chain = default_healing_chain_for_workflow(workflow_key, suggested_kind=suggested_kind)

    return _strategy_fingerprint(
        workflow_key=workflow_key,
        text=text,
        run=run,
        class_key=f"{workflow_key or 'unknown'}_failure",
        title=str(strategy.get("workflow_title") or ""),
        cause=str(remediation.get("human_action") or strategy.get("summary") or ""),
        fix_summary=str(strategy.get("summary") or "Apply the recommended automated fix."),
        chain=chain,
        confidence="medium" if chain else "low",
        requires_network=lane in ("provisioning_resume", "event_replay", "ai_retry"),
        safe_for_autopilot=workflow_key in ("tenant_school_provision", "marketplace_webhook_deliver_due"),
    )
