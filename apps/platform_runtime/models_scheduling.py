"""Durable per-job heartbeat for the in-process periodic scheduler.

PHASE 1 of the scheduler observability layer. The cache-based ``last_run`` in
``apps.platform_runtime.periodic`` is wiped on every deploy and expires ~2x
interval after the last run, so it cannot answer "has a scheduled job gone
silently dark?". This model is the DURABLE source of truth: exactly one row per
registered job, updated on every run, surviving deploys — the substrate for the
dead-man's-switch monitor (see ``scheduled_job_health``) that turns the
previously-silent "scheduled jobs stopped" failure into a loud, alertable one.
"""
from __future__ import annotations

from django.db import models

_JOB_NAME_MAX_LEN = 200  # magic-number-allow: job-name column width
_STATUS_MAX_LEN = 32


class ScheduledJobHeartbeat(models.Model):
    """Last-known execution state of one registered periodic job.

    Platform-level, NOT tenant-scoped: periodic jobs are platform-wide sweeps
    that themselves iterate tenants, so there is exactly one heartbeat per job
    name across the whole install (``job_name`` is unique).
    """

    job_name = models.CharField(max_length=_JOB_NAME_MAX_LEN, unique=True)
    expected_interval_seconds = models.PositiveIntegerField(default=0)
    last_started_at = models.DateTimeField(null=True, blank=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(max_length=_STATUS_MAX_LEN, blank=True, default="")
    last_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    consecutive_failures = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "scheduled job heartbeat"
        verbose_name_plural = "scheduled job heartbeats"
        ordering = ("job_name",)

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.job_name} [{self.last_status or 'pending'}]"
