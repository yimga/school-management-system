"""Roll up orchestration SLO metrics (Move 2)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.orchestration.models import (
    OrchestrationRun,
    OrchestrationSLOMetric,
    ProcessDefinition,
)


def _percentile(values: list[int], p: float) -> int:
    if not values:
        return 0
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round((p / 100.0) * (len(values) - 1)))))
    return int(values[k])


def aggregate_recent_window(*, window_minutes: int = 60) -> int:
    """Compute one OrchestrationSLOMetric row per ProcessDefinition.

    Returns the number of definition rows written.
    """

    now = timezone.now()
    window_end = now
    window_start = now - timedelta(minutes=window_minutes)
    count_written = 0

    for defn in ProcessDefinition.objects.all():
        runs = list(
            OrchestrationRun.objects.filter(  # tenant-isolation-allow: orchestration-slo-run-aggregate-all-tenants
                definition=defn, created_at__gte=window_start, created_at__lt=window_end
            )
        )
        latencies = []
        succeeded = 0
        failed = 0
        sla_breach = 0
        for r in runs:
            if r.completed_at and r.started_at:
                latencies.append(int((r.completed_at - r.started_at).total_seconds() * 1000))
            if r.status == OrchestrationRun.Status.COMPLETED:
                succeeded += 1
            if r.status == OrchestrationRun.Status.FAILED:
                failed += 1
            if r.sla_deadline and r.completed_at and r.completed_at > r.sla_deadline:
                sla_breach += 1
        total = len(runs)
        queue_depth = OrchestrationRun.objects.filter(  # tenant-isolation-allow: orchestration-slo-run-latency-aggregate
            definition=defn,
            status=OrchestrationRun.Status.PENDING,
            created_at__lt=window_end,
        ).count()
        success_rate = (succeeded / total) if total else 0.0

        OrchestrationSLOMetric.objects.update_or_create(
            definition=defn,
            window_start=window_start,
            defaults={
                "window_end": window_end,
                "runs_total": total,
                "runs_succeeded": succeeded,
                "runs_failed": failed,
                "runs_sla_breached": sla_breach,
                "p50_latency_ms": _percentile(latencies, 50),
                "p95_latency_ms": _percentile(latencies, 95),
                "p99_latency_ms": _percentile(latencies, 99),
                "queue_depth_max": queue_depth,
                "success_rate": success_rate,
            },
        )
        count_written += 1
    return count_written
