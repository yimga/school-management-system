"""School Lifecycle state machine.

A single append-only timeline that unifies the 4 lifecycle phases
(creation, onboarding, operation, offboarding/migration) so operators
can see the full 360 in one place.

Why a new app vs reusing SchoolProvisioningEvent:
- SchoolProvisioningEvent is creation-centric; its event_type vocabulary
  is owned by the wizard. Lifecycle needs a vocabulary that spans
  onboarding milestones (LAUNCH_READY), migration overlay states
  (MIGRATING), and reversible offboarding (GRACE) — none of which
  belong to the provisioning event taxonomy.
- Lifecycle is the spine other waves attach to (concierge, soft-delete,
  migration auto-launch). Keeping it isolated avoids entangling the
  schools-app migration graph.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class SchoolLifecycleStage(models.Model):
    class Stage(models.TextChoices):
        # Creation
        REQUESTED = "REQUESTED", "Requested"
        PROVISIONED = "PROVISIONED", "Provisioned"
        # Onboarding
        ONBOARDING_STARTED = "ONBOARDING_STARTED", "Onboarding started"
        ONBOARDING_LAUNCH_READY = "ONBOARDING_LAUNCH_READY", "Launch ready"
        # Steady-state operation
        OPERATING = "OPERATING", "Operating"
        # Migration overlay (can re-enter from OPERATING)
        MIGRATING = "MIGRATING", "Migrating"
        MIGRATION_COMPLETE = "MIGRATION_COMPLETE", "Migration complete"
        # Offboarding (reversible until PURGED)
        OFFBOARDING_REQUESTED = "OFFBOARDING_REQUESTED", "Offboarding requested"
        OFFBOARDING_EXPORTED = "OFFBOARDING_EXPORTED", "Export complete"
        OFFBOARDING_GRACE = "OFFBOARDING_GRACE", "In grace period"
        OFFBOARDING_CANCELLED = "OFFBOARDING_CANCELLED", "Offboarding cancelled"
        OFFBOARDING_PURGED = "OFFBOARDING_PURGED", "Purged"
        # Terminal failure (any phase)
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="lifecycle_stages",
    )
    stage = models.CharField(max_length=40, choices=Stage.choices, db_index=True)
    # SHA-256 hex prefix of the acting User.id (12 chars). PII-free —
    # never the raw user id or email. Empty string for system actors.
    actor_hash = models.CharField(max_length=12, blank=True, default="")
    # Operator-supplied note, capped at 200 chars. NEVER render raw PII.
    note = models.CharField(max_length=200, blank=True, default="")
    # Sanitized payload of facts about the transition. _sanitize_payload()
    # in services.py rejects sensitive keys before persisting.
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["stage", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.school_id} {self.stage} @ {self.created_at.isoformat() if self.created_at else '?'}"


# Lifecycle stages that are considered TERMINAL for the school.
# Once a school enters one of these the spine stops accepting new
# transitions except for revival (OFFBOARDING_PURGED is permanent).
TERMINAL_STAGES = frozenset({SchoolLifecycleStage.Stage.OFFBOARDING_PURGED})

# Stages that signal "school is actively serving real users".
LIVE_STAGES = frozenset(
    {
        SchoolLifecycleStage.Stage.OPERATING,
        SchoolLifecycleStage.Stage.MIGRATING,
        SchoolLifecycleStage.Stage.MIGRATION_COMPLETE,
    }
)


def _settings_school_field() -> str:
    # Defensive resolver: settings.AUTH_USER_MODEL is owned elsewhere.
    return getattr(settings, "AUTH_USER_MODEL", "auth.User")
