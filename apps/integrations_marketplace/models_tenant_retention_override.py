"""v4.00.83 — TenantRetentionOverride model.

Per-tenant overrides for retention sweep windows. Today retention runs
under env defaults (7y FERPA). Districts with state laws requiring
longer or shorter retention can record overrides here.

Lookup precedence (lms_retention_resolver):
  1. TenantRetentionOverride row for (tenant, table_name) -> years
  2. Env (RMC_LMS_RETENTION_<TABLE>_YEARS)
  3. Default 7 years
"""
from __future__ import annotations
from django.db import models


_TARGET_TABLE_CHOICES = (
    ("lms_diag_action_audit", "LMSDiagActionAudit"),
    ("lms_push_grade_audit", "LMSPushGradeAudit"),
    ("lms_token_rotation_chain", "LMSTokenRotationChain"),
    ("webhook_dead_letter", "WebhookDeadLetter"),
)


class TenantRetentionOverride(models.Model):
    """Per-tenant override for an audit table's retention window."""

    tenant_schema = models.CharField(max_length=64, db_index=True)
    target_table = models.CharField(max_length=64, choices=_TARGET_TABLE_CHOICES, db_index=True)
    retention_years = models.PositiveIntegerField(
        help_text="0 = retain forever. Otherwise rows older than this are eligible for sweep.",
    )
    reason = models.CharField(max_length=256, blank=True, default="",
                              help_text="Why this override exists (e.g. state law cite).")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    set_by_actor_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        verbose_name = "Tenant Retention Override"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant_schema", "target_table"],
                name="uniq_retention_override_per_tenant_table",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant_schema", "target_table"], name="rto_st_idx"),
        ]
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"TenantRetentionOverride({self.tenant_schema}, {self.target_table}, {self.retention_years}y)"
