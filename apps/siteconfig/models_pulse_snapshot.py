"""PlatformPulseSnapshot — daily snapshot rows for cockpit pulse deltas.

One row per (snapshot_date, metric_key). Captured by the daily management
command ``snapshot_platform_pulse`` (Celery beat at 01:15 UTC). Read by
``cockpit_platform_pulse_service._delta_for_card`` to compute the
"+3 this week" / "-2 this week" strings shown next to current values.

PII posture:
  Stores aggregate counts only — no per-tenant breakdowns, no slugs,
  no actor identifiers. Safe to surface in operator dashboards.

Retention:
  Append-only; old rows are pruned by an annual operator command, not
  on a hot path. The model has no FK, so backfilling is trivial.
"""
from __future__ import annotations

from django.db import models


class PlatformPulseSnapshot(models.Model):
    """One row per metric_key per UTC date.

    ``raw_value`` is the post-aggregation INTEGER (for currency we store
    whole-dollar units to keep delta math simple). ``display_value`` is the
    formatted string the resolver returned that day (e.g. "$42k", "15 / 249")
    so we can reproduce historical displays if needed.
    """

    SCHOOLS = "schools"
    INCIDENTS = "incidents"
    COUNTRIES = "countries"
    MRR = "mrr"
    WEBHOOKS = "webhooks"
    PIPELINE = "pipeline"
    METRIC_KEY_CHOICES = (
        (SCHOOLS, "Schools"),
        (INCIDENTS, "Incidents"),
        (COUNTRIES, "Countries"),
        (MRR, "MRR (whole dollars/month)"),
        (WEBHOOKS, "Webhooks drift"),
        (PIPELINE, "Pipeline (onboarding)"),
    )

    snapshot_date = models.DateField(db_index=True)
    metric_key = models.CharField(max_length=32, choices=METRIC_KEY_CHOICES, db_index=True)
    raw_value = models.BigIntegerField(default=0)
    display_value = models.CharField(max_length=64, blank=True, default="")
    captured_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "siteconfig"
        verbose_name = "Platform pulse snapshot"
        verbose_name_plural = "Platform pulse snapshots"
        constraints = [
            models.UniqueConstraint(
                fields=("snapshot_date", "metric_key"),
                name="uniq_pulse_snapshot_date_metric",
            ),
        ]
        indexes = [
            models.Index(fields=["metric_key", "-snapshot_date"], name="idx_pulse_metric_date_desc"),
        ]

    def __str__(self) -> str:
        return f"{self.snapshot_date} {self.metric_key}={self.display_value or self.raw_value}"
