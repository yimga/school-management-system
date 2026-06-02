"""Tenant-safe workflow visibility for school admins."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.workflow_registry import TAG_TENANT_SAFE, WORKFLOWS


def is_tenant_safe_workflow_key(workflow_key: str) -> bool:
    definition = WORKFLOWS.get(workflow_key or "")
    if definition is None:
        return False
    tags = tuple(getattr(definition, "default_tags", ()) or ())
    return TAG_TENANT_SAFE in tags


def sanitize_run_for_tenant(row: dict[str, Any]) -> dict[str, Any]:
    """Strip operator-only fields; keep progress shape."""

    rem = row.get("suggested_remediation") or {}
    safe_rem = {
        "human_action": str(rem.get("human_action", ""))[:300],
        "suggested_next": str(rem.get("suggested_next", ""))[:200],
        "auto_fix_available": bool(rem.get("auto_fix_available")),
    }
    return {
        "id": row.get("id"),
        "workflow_key": row.get("workflow_key"),
        "workflow_label": row.get("workflow_label"),
        "status": row.get("status"),
        "current_step_name": row.get("current_step_name"),
        "current_step_ordinal": row.get("current_step_ordinal"),
        "total_steps": row.get("total_steps"),
        "progress_percent": row.get("progress_percent"),
        "started_at": row.get("started_at"),
        "expected_duration_seconds": row.get("expected_duration_seconds"),
        "suggested_remediation": safe_rem,
    }


def list_tenant_trusted_runs(*, tenant_schema: str, limit: int = 15) -> list[dict[str, Any]]:
    from apps.platform_runtime.workflow_tracker import list_active_runs

    if not tenant_schema:
        return []
    rows = list_active_runs(tenant_schema=tenant_schema, actor_user_id="", limit=limit * 2)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not is_tenant_safe_workflow_key(str(row.get("workflow_key") or "")):
            continue
        out.append(sanitize_run_for_tenant(row))
        if len(out) >= limit:
            break
    return out
