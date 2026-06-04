"""Record workflow durations and expose p95 for degrading detection."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

_MAX_SAMPLES = 200


def record_completed_duration(*, workflow_key: str, duration_seconds: int) -> None:
    """Upsert rolling p50/p95 after a terminal run."""

    if not workflow_key or duration_seconds < 0:
        return
    try:
        from apps.platform_runtime.models import WorkflowDurationStat
    except Exception:
        return

    duration_seconds = min(int(duration_seconds), 86400)  # magic-number-allow: max-duration-cap-seconds
    try:
        stat, created = WorkflowDurationStat.objects.get_or_create(
            workflow_key=workflow_key[:80],
            defaults={
                "sample_count": 1,
                "p50_seconds": duration_seconds,
                "p95_seconds": duration_seconds,
            },
        )
        if created:
            return
        count = int(stat.sample_count or 0) + 1
        p50 = int(stat.p50_seconds or duration_seconds)
        p95 = int(stat.p95_seconds or duration_seconds)
        # Lightweight online blend — not a true percentile, good enough for degrading hints.
        p50 = int(round(p50 * 0.85 + duration_seconds * 0.15))
        p95 = max(p95, int(round(p95 * 0.92 + duration_seconds * 0.08)))
        if duration_seconds > p95:
            p95 = duration_seconds
        WorkflowDurationStat.objects.filter(pk=stat.pk).update(
            sample_count=min(count, _MAX_SAMPLES),
            p50_seconds=p50,
            p95_seconds=p95,
            updated_at=timezone.now(),
        )
    except Exception:
        logger.debug("workflow_duration_stat_record_failed key=%s", workflow_key, exc_info=True)


def duration_from_run(run: Any) -> int:
    started = getattr(run, "started_at", None)
    ended = getattr(run, "ended_at", None) or timezone.now()
    if started is None:
        return 0
    try:
        return max(0, int((ended - started).total_seconds()))
    except Exception:
        return 0


def get_p95_seconds(workflow_key: str) -> int:
    if not workflow_key:
        return 0
    try:
        from apps.platform_runtime.models import WorkflowDurationStat

        stat = WorkflowDurationStat.objects.filter(workflow_key=workflow_key[:80]).first()
        if stat is None:
            return 0
        return int(stat.p95_seconds or 0)
    except Exception:
        return 0
