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
            return out

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


def _try_ai_diagnosis(
    *,
    error_type: str,
    error_message: str,
    workflow_key: str,
) -> dict[str, Any] | None:
    """Best-effort AI diagnosis via ``services.ai_helpers``. Returns ``None``
    on any failure (import error, gateway unavailable, parse failure)."""

    try:
        from services import ai_helpers  # type: ignore[attr-defined]
    except Exception:
        return None

    invoke = getattr(ai_helpers, "invoke_with_request", None)
    if not callable(invoke):
        return None

    prompt = (
        "A platform workflow failed. Diagnose the most likely cause and "
        "suggest ONE concrete remediation in JSON.\n\n"
        f"workflow_key: {workflow_key}\n"
        f"error_type: {error_type}\n"
        f"error_message: {error_message[:400]}\n\n"
        "Respond with JSON only: "
        '{"remediation_key": "<short_slug>", "human_action": "<one sentence>", '
        '"auto_fix_available": false, "suggested_next": "<one sentence>"}'
    )

    try:
        # NOTE: ai_helpers.invoke_with_request needs a request; for unattended
        # auto-fix lookups, we pass request=None and let the helper either
        # accept it (cloud profile w/ system identity) or refuse cleanly.
        response = invoke(
            request=None,
            prompt=prompt,
            purpose="workflow_auto_fix",
            max_tokens=200,
        )
    except Exception:
        logger.warning("workflow_auto_fix_ai_invoke_failed key=%s", workflow_key)
        return None

    if not response:
        return None

    text = ""
    if isinstance(response, dict):
        text = str(response.get("text") or response.get("output") or "")
    else:
        text = str(response)

    if not text:
        return None

    import json

    try:
        parsed = json.loads(text)
    except Exception:
        # Try to find a JSON object inside the text.
        match = re.search(r"\{[^{}]*\}", text)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None

    if not isinstance(parsed, dict):
        return None

    return {
        "verdict": "ai_match",
        "remediation_key": str(parsed.get("remediation_key", "ai_suggested"))[:64],
        "human_action": str(parsed.get("human_action", ""))[:400],
        "auto_fix_available": bool(parsed.get("auto_fix_available", False)),
        "suggested_next": str(parsed.get("suggested_next", ""))[:200],
    }
