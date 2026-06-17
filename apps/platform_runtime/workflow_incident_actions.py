"""Bulk operator actions for cross-tenant workflow incident clusters."""

from __future__ import annotations

from typing import Any

from django.utils import timezone
from django.utils.translation import gettext as _


def enrich_incident_row(incident: dict[str, Any]) -> dict[str, Any]:
    """Add operator-facing bulk actions to a clustered incident row."""

    out = dict(incident)
    run_ids = list(out.get("run_ids") or [])
    auto_fix_kind = str(out.get("auto_fix_kind") or "").strip()
    bulk_available = bool(out.get("bulk_apply_available") and auto_fix_kind and run_ids)
    actions: list[dict[str, Any]] = []
    if bulk_available:
        actions.append(
            {
                "kind": "bulk_apply_fix",
                "label": _("Apply fix to all eligible runs"),
                "primary": True,
                "remediation_key": out.get("remediation_key", ""),
                "run_count": len(run_ids),
            }
        )
    out["operator_actions"] = actions
    return out


def bulk_apply_incident_remediation(
    *,
    remediation_key: str,
    actor_user_id: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Apply auto-fix to eligible runs in an incident cluster (staff-only caller)."""

    from apps.platform_runtime.models import WorkflowRun
    from apps.platform_runtime.workflow_autopilot import record_apply_log
    from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind
    from apps.platform_runtime.workflow_flight_deck_actions import (
        resolve_effective_remediation,
    )
    from apps.platform_runtime.workflow_incidents import runs_for_remediation_key

    key = str(remediation_key or "").strip()
    if not key:
        return {"ok": False, "reason": "missing_remediation_key"}

    runs = runs_for_remediation_key(remediation_key=key, limit=max(1, min(limit, 50)))
    applied = 0
    skipped = 0
    failed = 0
    results: list[dict[str, Any]] = []

    for run in runs:
        remediation = resolve_effective_remediation(run)
        if not remediation.get("auto_fix_available"):
            skipped += 1
            continue
        kind = str(remediation.get("auto_fix_kind") or "").strip()
        if not kind:
            skipped += 1
            continue
        result = apply_auto_fix_kind(run=run, kind=kind)
        row = {"run_id": run.pk, "kind": kind, "ok": bool(result.get("ok"))}
        if result.get("ok"):
            applied += 1
            record_apply_log(
                run_id=run.pk,
                workflow_key=run.workflow_key,
                auto_fix_kind=kind,
                outcome="applied",
                actor_user_id=actor_user_id,
                autopilot=False,
            )
        else:
            failed += 1
            row["reason"] = result.get("reason", "apply_failed")
        results.append(row)

    return {
        "ok": applied > 0 or (failed == 0 and skipped > 0),
        "remediation_key": key,
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "results": results[:20],
        "generated_at": timezone.now().isoformat(),
    }
