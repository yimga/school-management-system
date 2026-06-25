"""Workflow Progress Bus — auto-fix matcher (v4.00.96).

Maps a workflow's terminal error (type + message) to a concrete remediation
the frontend chip can surface to the operator. Two paths:

* **Fast deterministic match** — regex over a curated taxonomy. Returns
  ``{"verdict": "match", "remediation_key": "...", "human_action": "...",
  "auto_fix_available": bool}`` with zero AI cost.
* **AI fallback** — when no regex matches, route to the platform's
  ``services.ai_helpers`` (NEVER ``services.ai_gateway`` directly per the
  architectural boundary). Best-effort; on AI failure returns the safe
  no-match envelope.

The remediation payload is JSON-serializable; the frontend renders it as a
slide-in card with an "Apply" button when ``auto_fix_available`` is True.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# Curated taxonomy. Each entry: (regex over "<ErrType>: <message>"),
# (verdict envelope). Order matters — first match wins, most specific first.
_TAXONOMY: tuple[tuple[re.Pattern[str], dict[str, Any]], ...] = (
    # User creation
    (
        re.compile(r"(IntegrityError|UNIQUE constraint failed).*(email|username)", re.IGNORECASE),
        {
            "remediation_key": "user_email_or_username_collision",
            "human_action": "A user with this email or username already exists. Open the existing record or pick a different value.",
            "auto_fix_available": False,
            "suggested_next": "Search the existing user directory.",
        },
    ),
    (
        re.compile(r"ValidationError.*email", re.IGNORECASE),
        {
            "remediation_key": "user_email_invalid",
            "human_action": "The email address is malformed. Check for typos or missing the @ symbol.",
            "auto_fix_available": False,
            "suggested_next": "Re-enter the email address.",
        },
    ),
    # Tenant creation
    (
        re.compile(r"(IntegrityError|UNIQUE).*(schema_name|subdomain|slug)", re.IGNORECASE),
        {
            "remediation_key": "tenant_slug_collision",
            "human_action": "This tenant slug or subdomain is already taken. Pick an alternate (e.g. add a year or region suffix).",
            "auto_fix_available": True,
            "auto_fix_kind": "suggest_alternate_slug",
            "suggested_next": "Try slug-2026 or slug-academy.",
        },
    ),
    (
        re.compile(r"OperationalError.*(database|schema).*already exists", re.IGNORECASE),
        {
            "remediation_key": "tenant_schema_already_exists",
            "human_action": "The tenant database schema already exists. If this is a re-run, mark the previous attempt cancelled and retry.",
            "auto_fix_available": False,
            "suggested_next": "Open the tenant lifecycle inspector.",
        },
    ),
    # OAuth / integration
    (
        re.compile(r"(invalid_grant|invalid_client|unauthorized_client)", re.IGNORECASE),
        {
            "remediation_key": "oauth_credentials_invalid",
            "human_action": "The upstream LMS rejected the OAuth credentials. Verify the client_id / client_secret and confirm the tenant is whitelisted.",
            "auto_fix_available": False,
            "suggested_next": "Re-run the integration handshake from the marketplace.",
        },
    ),
    (
        re.compile(r"(token.*expired|expired.*token|TokenExpired)", re.IGNORECASE),
        {
            "remediation_key": "oauth_token_expired",
            "human_action": "The access token expired mid-workflow. Auto-refresh will retry the workflow once.",
            "auto_fix_available": True,
            "auto_fix_kind": "refresh_oauth_token_and_retry",
            "suggested_next": "Click Apply to refresh + retry.",
        },
    ),
    # Tenant provisioning (owner-safe auto-fix kinds)
    (
        re.compile(
            r"(KombuOperationalError|BrokerNotAvailable|celery.*unavailable|queue unavailable)",
            re.IGNORECASE,
        ),
        {
            "remediation_key": "provisioning_queue_unavailable",
            "human_action": "Setup could not reach the background worker. Tap Try again to re-run setup now.",
            "auto_fix_available": True,
            "auto_fix_kind": "requeue_provision",
            "suggested_next": "Retry provisioning.",
        },
    ),
    (
        re.compile(r"(welcome.*email|send_welcome|SMTP|mail delivery)", re.IGNORECASE),
        {
            "remediation_key": "provisioning_welcome_email_failed",
            "human_action": "Your portal is almost ready but the welcome email did not send. Tap Try again to resend it.",
            "auto_fix_available": True,
            "auto_fix_kind": "resend_welcome",
            "suggested_next": "Resend welcome email.",
        },
    ),
    (
        re.compile(r"(DNS|subdomain|domain.*sync|nameserver)", re.IGNORECASE),
        {
            "remediation_key": "provisioning_dns_sync_failed",
            "human_action": "Your portal address needs another DNS sync. Tap Try again to retry.",
            "auto_fix_available": True,
            "auto_fix_kind": "retry_dns_sync",
            "suggested_next": "Retry DNS sync.",
        },
    ),
    # Network / upstream
    (
        re.compile(r"(ConnectionError|Timeout|ReadTimeout|ConnectTimeout)", re.IGNORECASE),
        {
            "remediation_key": "upstream_timeout",
            "human_action": "Upstream service did not respond in time. This is often transient — retry, then check the integration health page if it persists.",
            "auto_fix_available": True,
            "auto_fix_kind": "retry_once_with_backoff",
            "suggested_next": "Click Apply to retry with 30-second backoff.",
        },
    ),
    (
        re.compile(r"HTTPError.*5\d\d", re.IGNORECASE),
        {
            "remediation_key": "upstream_5xx",
            "human_action": "Upstream service returned a server error. Likely transient — retry, then check the upstream status page.",
            "auto_fix_available": True,
            "auto_fix_kind": "retry_once_with_backoff",
            "suggested_next": "Click Apply to retry.",
        },
    ),
    (
        re.compile(r"HTTPError.*429", re.IGNORECASE),
        {
            "remediation_key": "upstream_rate_limit",
            "human_action": "Upstream rate limit hit. Wait the Retry-After window and retry — auto-retry will honor the upstream's Retry-After header.",
            "auto_fix_available": True,
            "auto_fix_kind": "retry_after_rate_limit",
            "suggested_next": "Click Apply to retry once rate limit clears.",
        },
    ),
    # Permission / tenant scoping
    (
        re.compile(r"(PermissionDenied|Forbidden|403)", re.IGNORECASE),
        {
            "remediation_key": "permission_denied",
            "human_action": "The acting user lacks permission for this workflow. Promote the user's role or have an operator re-run.",
            "auto_fix_available": False,
            "suggested_next": "Open the role + permission matrix.",
        },
    ),
    # OneRoster / bulk import
    (
        re.compile(r"(invalid_row|validation_failed|missing_required)", re.IGNORECASE),
        {
            "remediation_key": "oneroster_invalid_row",
            "human_action": "One or more rows failed validation. Open the bulk import detail to see per-row errors and fix the source file.",
            "auto_fix_available": False,
            "suggested_next": "Download the per-row error CSV.",
        },
    ),
    # Generic database
    (
        re.compile(r"(IntegrityError|OperationalError|DatabaseError)", re.IGNORECASE),
        {
            "remediation_key": "database_error_generic",
            "human_action": "A database error occurred. Open the workflow detail for the full traceback; retry if the operation is idempotent.",
            "auto_fix_available": False,
            "suggested_next": "Open the workflow detail.",
        },
    ),
)


def suggest_remediation(
    *,
    error_type: str,
    error_message: str,
    workflow_key: str = "",
) -> dict[str, Any]:
    """Return a JSON-serializable remediation envelope for the given error.

    Resolution order:
    1. Walk the curated regex taxonomy. First hit wins.
    2. If no match, fall back to AI diagnosis via ``services.ai_helpers``
       (best-effort; on any failure returns the safe no-match envelope).
    """

    combined = f"{error_type}: {error_message}"
    for pattern, envelope in _TAXONOMY:
        if pattern.search(combined):
            out = dict(envelope)
            out["verdict"] = "match"
            out["matched_pattern"] = pattern.pattern[:80]
            if workflow_key == "tenant_school_provision" and not out.get("auto_fix_available"):
                return _provision_requeue_envelope(out)
            return out

    if workflow_key == "tenant_school_provision":
        return _provision_requeue_envelope()

    from apps.platform_runtime.workflow_healing_chains import (
        default_healing_chain_for_workflow,
    )

    strategy_chain = default_healing_chain_for_workflow(workflow_key)
    if strategy_chain:
        from apps.platform_runtime.workflow_recovery_playbook import (
            recovery_strategy_for_workflow,
        )

        strategy = recovery_strategy_for_workflow(workflow_key)
        return {
            "verdict": "strategy_match",
            "remediation_key": f"{workflow_key}_auto_heal",
            "human_action": str(strategy.get("summary") or "Apply the recommended automated fix."),
            "auto_fix_available": True,
            "auto_fix_kind": strategy_chain[0],
            "suggested_next": " → ".join(strategy_chain[:3]),
            "healing_chain": strategy_chain,
        }

    # Unknown — try AI diagnosis via the platform's allowed bridge.
    ai_envelope = _try_ai_diagnosis(
        error_type=error_type,
        error_message=error_message,
        workflow_key=workflow_key,
    )
    if ai_envelope is not None:
        return ai_envelope

    return {
        "verdict": "no_match",
        "remediation_key": "unknown_error",
        "human_action": "No automatic remediation found. Open the workflow run detail to inspect the traceback.",
        "auto_fix_available": False,
        "suggested_next": "Inspect the workflow run detail.",
    }


def _provision_requeue_envelope(prior: dict[str, Any] | None = None) -> dict[str, Any]:
    """Owner-safe provisioning failures always offer idempotent requeue."""

    base = dict(prior or {})
    base.update(
        {
            "verdict": "provision_requeue",
            "remediation_key": base.get("remediation_key") or "provisioning_step_failed",
            "human_action": (
                "School setup failed partway through. Re-queue provisioning — the job "
                "is idempotent and resumes from the last safe checkpoint."
            ),
            "auto_fix_available": True,
            "auto_fix_kind": "requeue_provision",
            "suggested_next": "Apply fix from Flight Deck or the workflow progress chip.",
        }
    )
    return base


def _try_ai_diagnosis(
    *,
    error_type: str,
    error_message: str,
    workflow_key: str,
    request: Any | None = None,
) -> dict[str, Any] | None:
    """Best-effort AI diagnosis via workflow-aware invoker."""

    try:
        from apps.platform_runtime.workflow_error_classifier import ErrorFingerprint
        from apps.platform_runtime.workflow_healing_ai import ai_diagnosis_for_run
    except Exception:
        return None

    stub = ErrorFingerprint(
        class_key="auto_fix_fallback",
        human_title="Workflow failure",
        human_cause=f"{error_type}: {error_message[:200]}",
        human_fix_summary="Inspect run detail or apply an automated fix when available.",
        recommended_chain=[],
        confidence="low",
    )

    class _RunStub:
        workflow_key = workflow_key
        error_summary = {"type": error_type, "message": error_message}
        suggested_remediation = {}
        payload_summary = {}

    ai = ai_diagnosis_for_run(run=_RunStub(), fingerprint=stub, request=request)
    if not ai:
        return None

    return {
        "verdict": "ai_match",
        "remediation_key": str(ai.get("title", "ai_suggested"))[:64].lower().replace(" ", "_"),
        "human_action": str(ai.get("cause", ""))[:400],
        "auto_fix_available": bool(ai.get("auto_fix_available")),
        "auto_fix_kind": (ai.get("recommended_chain") or [None])[0],
        "suggested_next": " → ".join(ai.get("plan") or [])[:200],
        "diagnosis_source": "ai_assisted",
    }
