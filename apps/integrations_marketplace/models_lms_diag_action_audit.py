"""v4.00.62 — Dedicated LMS diagnostics action-audit log.

Cleans up v4.00.61's reuse of ``LMSPushGradeAudit`` with a
``course_id="_diag_action"`` discriminator. That worked but mixed
operator-action rows with push-grade rows in the same table, which made
exports + retention sweeps awkward.

This model owns ONE concern only: every operator click on the LMS
diagnostics dashboard (force-refresh / force-rotate) gets exactly one
row, with explicit columns for what was clicked + the outcome counters
(considered / ok / failed) rather than parsed from a free-form
``detail`` string.

PII-safe by design: ``actor_hash`` is SHA-256[:12] of the actor's
username; raw username never lands.
"""
from __future__ import annotations

from django.db import models


class LMSDiagActionAudit(models.Model):
    """One row per force-refresh / force-rotate click."""

    action = models.CharField(
        max_length=32,
        db_index=True,
        help_text="force_refresh | force_rotate (or future action names).",
    )
    provider = models.CharField(max_length=24, db_index=True)
    actor_hash = models.CharField(
        max_length=16,
        blank=True,
        default="",
        help_text="SHA-256[:12] of the actor's username (PII-free).",
    )
    actor_user_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Actor user pk (string for UUID/int compatibility).",
    )
    considered = models.IntegerField(default=0)
    ok_count = models.IntegerField(default=0)
    failed_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "integrations_marketplace"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["action", "created_at"],
                name="integration_action_diag_idx",
            ),
            models.Index(
                fields=["provider", "created_at"],
                name="integration_prov_diag_idx",
            ),
        ]
        verbose_name = "LMS diag action audit"
        verbose_name_plural = "LMS diag action audits"

    def __str__(self) -> str:
        return f"{self.action}/{self.provider} ok={self.ok_count} failed={self.failed_count}"
