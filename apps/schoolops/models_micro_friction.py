"""Persistent storage for substitute-handover and lost-belongings workflows."""

from __future__ import annotations

from django.conf import settings
from django.db import models

_AUTH_USER_MODEL = getattr(settings, "AUTH_USER_MODEL", "accounts.User")


class SubstituteHandoverPacketRecord(models.Model):
    """Durable handover packet minted online or replayed from offline queue."""

    class Source(models.TextChoices):
        ONLINE = "online", "Online form"
        OFFLINE = "offline", "Offline sync"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="substitute_handover_packets",
    )
    packet_id = models.CharField(max_length=36, db_index=True)
    teacher_id_hash = models.CharField(max_length=12)
    substitute_id_hash = models.CharField(max_length=12)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    lesson_outline = models.JSONField(default=list, blank=True)
    seating_chart_ref = models.CharField(max_length=128, blank=True, default="")
    medical_iep_gated = models.BooleanField(default=True)
    reason_code = models.CharField(max_length=64, default="unspecified")
    audit_event_id = models.CharField(max_length=36, blank=True, default="")
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.ONLINE,
    )
    created_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="substitute_handover_packets_created",
    )
    client_offline_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_substitute_handover_packet"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "packet_id"],
                name="uniq_handover_packet_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "valid_until"]),
        ]

    def __str__(self) -> str:
        return f"handover:{self.packet_id[:8]}…"


class LostBelongingsTagRecord(models.Model):
    """QR tag row resolvable by short_code within a tenant."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RECOVERED = "recovered", "Recovered"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="lost_belongings_tags",
    )
    asset_id = models.CharField(max_length=128)
    short_code = models.CharField(max_length=32)
    label_hint = models.CharField(max_length=80)
    tenant_id_hash = models.CharField(max_length=12)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_by = models.ForeignKey(
        _AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lost_belongings_tags_created",
    )
    client_offline_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    recovered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_lost_belongings_tag"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "short_code"],
                name="uniq_lost_tag_short_code_per_school",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.short_code} ({self.label_hint[:24]})"


class LostBelongingsCustodyEventRecord(models.Model):
    """Append-only custody line for a tag (finder sighting or staff recovery)."""

    class ActorKind(models.TextChoices):
        ANONYMOUS_FINDER = "anonymous_finder", "Anonymous finder"
        STAFF = "staff", "Staff"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="lost_belongings_custody_events",
    )
    tag = models.ForeignKey(
        LostBelongingsTagRecord,
        on_delete=models.CASCADE,
        related_name="custody_events",
    )
    event_id = models.CharField(max_length=36, db_index=True)
    actor_kind = models.CharField(max_length=24, choices=ActorKind.choices)
    notes_redacted = models.CharField(max_length=280, blank=True, default="")
    parent_notified = models.BooleanField(default=False)
    staff_id_hash = models.CharField(max_length=12, blank=True, default="")
    occurred_at = models.DateTimeField()
    client_offline_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_lost_belongings_custody_event"
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "event_id"],
                name="uniq_custody_event_id_per_school",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.actor_kind}:{self.event_id[:8]}…"
