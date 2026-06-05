"""Agentic AI action audit log (Phase 1 — read-only rollout).

Durable, append-only record of every agentic action *proposed* and *executed*
through the Phase-1 orchestration (``services.ai_agentic_service``). This closes
gap **G4** from ``docs/AI_AGENTIC_ACTIONS_DESIGN.md`` — the kernel's
``execute_action(audit_sink=…)`` callable now has a real durable sink.

Privacy contract (mirrors ``apps.migration_cloud.models_audit``):
- NEVER store raw user ids, raw action params, or PII. The actor and confirmer
  are stored as ``sha256[:12]`` hashes; params are stored as a ``sha256[:16]``
  hash of their canonical JSON. Tenant scope is the school identifier (not PII).
- Append-only: ``save()`` refuses updates, ``delete()`` always raises, and the
  default manager blocks ``QuerySet.delete()``.
"""

from __future__ import annotations

from django.db import models

from apps.platform_runtime.append_only import (
    AppendOnlyManager,
    AppendOnlyModelMixin,
)


class AIAgenticActionAuditReadOnlyError(Exception):
    """Raised when code attempts to mutate an append-only agentic audit row."""


class AIAgenticActionOutcome(models.TextChoices):
    OK = "ok", "Ok"
    BLOCKED = "blocked", "Blocked"
    ERROR = "error", "Error"


class AIAgenticActionAudit(AppendOnlyModelMixin, models.Model):
    """One row per agentic action proposal/execution attempt.

    Written by ``services.ai_agentic_service`` via the kernel's ``audit_sink``.
    Read by the operator AI-Center agentic surface (most-recent-first tail).
    """

    audit_id = models.CharField(max_length=32, unique=True, db_index=True)
    tenant_id = models.CharField(max_length=128, blank=True, default="")
    actor_user_id_hash = models.CharField(max_length=16, blank=True, default="")
    confirmed_by_hash = models.CharField(max_length=16, blank=True, default="")
    action = models.CharField(max_length=128)
    impact = models.CharField(max_length=16, blank=True, default="")
    params_hash = models.CharField(max_length=32, blank=True, default="")
    executed = models.BooleanField(default=False)
    outcome = models.CharField(
        max_length=16,
        choices=AIAgenticActionOutcome.choices,
        default=AIAgenticActionOutcome.OK,
    )
    blocked_reason = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AppendOnlyManager()

    class Meta:
        app_label = "platform_runtime"
        verbose_name = "AI agentic action audit"
        verbose_name_plural = "AI agentic action audits"
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=["tenant_id", "created_at"],
                name="agentic_audit_tenant_idx",
            ),
            models.Index(
                fields=["action", "created_at"],
                name="agentic_audit_action_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — admin/debug only
        return f"{self.action} [{self.outcome}] {self.audit_id}"

    def save(self, *args, **kwargs):
        # Append-only: refuse any update to an existing row.
        if self.pk is not None:
            raise AIAgenticActionAuditReadOnlyError(
                "AIAgenticActionAudit rows are append-only and cannot be updated."
            )
        super().save(*args, **kwargs)
