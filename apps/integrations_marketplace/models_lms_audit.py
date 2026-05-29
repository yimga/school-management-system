"""v4.00.52 — LMS adapter audit log (Wedge 2).

Append-only record of every grade-push attempted through the
``apps.api.lms_adapters`` SOT. PII-safe by design: user_id is hashed via
SHA-256 (first 16 hex chars) so the audit row can be retained
indefinitely without holding raw learner identifiers.
"""
from __future__ import annotations

import hashlib

from django.db import models


def _hash16(raw: str) -> str:
    """First 16 hex chars of SHA-256(raw). Empty string → empty."""
    if not raw:
        return ""
    return hashlib.sha256(str(raw).encode("utf-8")).hexdigest()[:16]


class LMSPushGradeAudit(models.Model):
    """One row per push_grade attempt.

    Stores OUTCOME + identifiers HASHED. The score is stored as a
    rounded string so the row holds the intent without the precise
    learner-aligned value.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lms_push_grade_audits",
    )
    provider = models.CharField(max_length=24, db_index=True)
    course_id = models.CharField(max_length=128)
    assignment_id = models.CharField(max_length=128)
    user_hash = models.CharField(
        max_length=32,
        db_index=True,
        help_text="SHA-256[:16] of the LMS user_id (PII-free).",
    )
    score_text = models.CharField(max_length=16, blank=True, default="")
    ok = models.BooleanField(default=False)
    status_code = models.IntegerField(default=0)
    detail = models.CharField(max_length=255, blank=True, default="")
    actor_user_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Operator user pk who triggered the push (string for UUID/int compatibility).",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        app_label = "integrations_marketplace"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["school", "provider"]),
            models.Index(fields=["ok", "created_at"]),
        ]
        verbose_name = "LMS push-grade audit"
        verbose_name_plural = "LMS push-grade audits"

    def __str__(self) -> str:
        return f"{self.provider}/{self.assignment_id} → {self.user_hash} ({self.ok})"
