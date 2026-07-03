"""Derived-value lineage — record-level provenance for computed outputs.

9.8 lineage wave (2026-07-02). The metadata app already answers the
design-time lineage question ("what uses this entity/field") via
``MetadataDependency`` + ``lineage_api``; what the platform could NOT answer
was the record-level one: *which rows produced this report-card average /
this at-risk score?* Derived values were computed and persisted with zero
record of their inputs — the most consequential numbers were the least
traceable.

One ``DerivedValueLineage`` row is written (best-effort, never blocking the
compute path) each time a derived output is persisted. Inputs are recorded
at the granularity the computation honestly supports, and say so:

  * ``row``   — explicit input PKs (e.g. the Evaluation rows behind a term
                report card)
  * ``scope`` — a queryset descriptor (model + filter scope + window) where
                the computation aggregates without materializing PKs (e.g.
                the nightly at-risk score's feature windows)
"""
from __future__ import annotations

import logging
import uuid

from django.db import models

logger = logging.getLogger(__name__)

_MAX_INPUT_ENTRIES = 500
_BODY_GRANULARITIES = ("row", "scope")


class DerivedValueLineage(models.Model):
    """Where a persisted derived value came from."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="derived_value_lineage",
    )
    output_model = models.CharField(
        max_length=100, help_text='Dotted label of the output row, e.g. "reports.ReportCard".'
    )
    output_pk = models.CharField(max_length=64)
    computation = models.CharField(
        max_length=100,
        db_index=True,
        help_text='Stable computation name, e.g. "report_card.term" / "analytics.nightly_risk".',
    )
    computation_version = models.CharField(max_length=64, blank=True, default="")
    granularity = models.CharField(
        max_length=8,
        choices=[(g, g) for g in _BODY_GRANULARITIES],
        default="row",
    )
    inputs = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "row granularity: [{model, pk}, …]; scope granularity: "
            "[{model, scope: {…}}, …]. Capped; truncation is flagged."
        ),
    )
    inputs_truncated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "metadata"
        verbose_name = "Derived value lineage"
        verbose_name_plural = "Derived value lineage"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "output_model", "output_pk"]),
            models.Index(fields=["computation", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.output_model}#{self.output_pk} ← {self.computation}"


def record_derived_lineage(
    *,
    output,
    computation: str,
    inputs: list,
    granularity: str = "row",
    version: str = "",
    school=None,
):
    """Best-effort lineage write — never breaks the compute path that calls it."""
    try:
        if not getattr(output, "pk", None):
            # A lineage row that can't identify its output is noise, not
            # provenance — refuse quietly (unsaved or non-model outputs).
            return None
        entries = list(inputs or [])
        truncated = len(entries) > _MAX_INPUT_ENTRIES
        if truncated:
            entries = entries[:_MAX_INPUT_ENTRIES]
        if granularity not in _BODY_GRANULARITIES:
            granularity = "row"
        meta = getattr(output, "_meta", None)
        output_model = f"{meta.app_label}.{meta.object_name}" if meta else str(type(output).__name__)
        return DerivedValueLineage.objects.create(
            school=school if school is not None else getattr(output, "school", None),
            output_model=output_model,
            output_pk=str(getattr(output, "pk", ""))[:64],
            computation=computation,
            computation_version=str(version or "")[:64],
            granularity=granularity,
            inputs=entries,
            inputs_truncated=truncated,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "derived_lineage.record_failed computation=%s err=%s", computation, exc
        )
        return None


def lineage_for(output):
    """Newest-first lineage rows for one persisted output."""
    meta = getattr(output, "_meta", None)
    output_model = f"{meta.app_label}.{meta.object_name}" if meta else str(type(output).__name__)
    return DerivedValueLineage.objects.filter(  # tenant-isolation-allow: lineage-query-scoped-by-output-row-identity
        output_model=output_model, output_pk=str(getattr(output, "pk", ""))[:64]
    )


def risk_scope_inputs(student_pk, window_days: int, model_version: str) -> list[dict]:
    """Honest scope-granularity inputs for the nightly at-risk score.

    The feature extractor aggregates per-student windows without materializing
    PKs, so lineage records the queryset scopes it actually read.
    """
    scope = {"student": str(student_pk), "window_days": int(window_days)}
    return [
        {"model": "academics.Attendance", "scope": scope},
        {"model": "evals.Evaluation", "scope": scope},
        {"model": "finance.Invoice", "scope": {"student": str(student_pk)}},
        {"model": "analytics.MLModel", "scope": {"version": model_version or "heuristic"}},
    ]


__all__ = [
    "DerivedValueLineage",
    "record_derived_lineage",
    "lineage_for",
    "risk_scope_inputs",
]
