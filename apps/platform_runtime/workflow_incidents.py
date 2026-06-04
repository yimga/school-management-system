"""Cross-tenant remediation clustering for operator Flight Deck."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.utils import timezone


def cluster_recent_incidents(*, hours: int = 24, min_tenants: int = 2) -> list[dict[str, Any]]:
    """Group recent failed/stuck runs by remediation_key (staff-only data)."""

    try:
        from apps.platform_runtime.models import WorkflowRun
    except Exception:
        return []

    since = timezone.now() - timedelta(hours=max(hours, 1))
    qs = WorkflowRun.objects.filter(  # tenant-isolation-allow: operator-flight-deck-cross-tenant-incident-cluster
        status__in=("failed", "stuck", "running"),
        started_at__gte=since,
    ).order_by("-started_at")[:500]

    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "remediation_key": "",
            "tenant_hashes": set(),
            "run_count": 0,
            "workflow_keys": set(),
            "sample_action": "",
        }
    )

    for run in qs:
        rem = run.suggested_remediation or {}
        if run.status == "running":
            from apps.platform_runtime.workflow_tracker import is_stuck

            if not is_stuck(run):
                continue
        err = run.error_summary if isinstance(run.error_summary, dict) else {}
        key = str(rem.get("remediation_key") or err.get("type") or "unknown")
        bucket = buckets[key]
        bucket["remediation_key"] = key
        bucket["run_count"] += 1
        if run.tenant_schema:
            bucket["tenant_hashes"].add(run.tenant_schema[:12])
        bucket["workflow_keys"].add(run.workflow_key)
        if not bucket["sample_action"] and rem.get("human_action"):
            bucket["sample_action"] = str(rem["human_action"])[:200]

    out: list[dict[str, Any]] = []
    for key, bucket in buckets.items():
        tenant_count = len(bucket["tenant_hashes"])
        if tenant_count < min_tenants and bucket["run_count"] < 3:
            continue
        out.append(
            {
                "remediation_key": key,
                "run_count": bucket["run_count"],
                "tenant_count": tenant_count,
                "tenant_hashes": sorted(bucket["tenant_hashes"])[:12],
                "workflow_keys": sorted(bucket["workflow_keys"])[:8],
                "sample_action": bucket["sample_action"],
            }
        )
    out.sort(key=lambda row: (-row["run_count"], -row["tenant_count"]))
    return out[:20]
