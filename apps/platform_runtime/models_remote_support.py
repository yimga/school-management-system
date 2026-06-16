"""Remote Support — the session spine (one operator helping one tenant).

This model owns the consent + channel + lifecycle + diagnostics + audit spine.
It COMPOSES the existing engines rather than replacing them:

- the support CASE is a ``GlobalSupportTicket`` (soft reference by id — no hard
  FK, so this SHARED-schema model never couples to siteconfig's schema
  placement);
- acting-AS the tenant is the existing assist_dock impersonation (a session can
  assist WITHOUT it — ``impersonation_used`` records whether it was);
- OFFLINE delivery rides the existing ``OfflineAction`` queue and the
  ``OperatorIntent`` reverse channel (P4).

Lives in ``platform_runtime`` (SHARED_APPS / public schema) so the operator
console can read every tenant's sessions.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


class RemoteSupportSession(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ACCEPTED = "accepted", "Accepted"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        DECLINED = "declined", "Declined"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    class Channel(models.TextChoices):
        ONLINE = "online", "Online (near real-time)"
        OFFLINE_ASYNC = "offline_async", "Offline (queued, syncs on reconnect)"

    class Initiator(models.TextChoices):
        TENANT = "tenant", "Tenant requested"
        OPERATOR = "operator", "Operator proposed"

    OPEN_STATUSES = (Status.REQUESTED, Status.ACCEPTED, Status.ACTIVE)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="remote_support_sessions",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remote_support_requests",
        help_text="Tenant user who asked for help (null when operator-proposed).",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remote_support_sessions",
        help_text="Assigned platform operator (or in-school support person).",
    )
    initiator = models.CharField(
        max_length=16, choices=Initiator.choices, default=Initiator.TENANT
    )
    channel = models.CharField(
        max_length=16, choices=Channel.choices, default=Channel.ONLINE
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.REQUESTED,
        db_index=True,
    )
    reason = models.CharField(max_length=500, blank=True)

    # Soft reference to the support case (GlobalSupportTicket UUID). No FK.
    support_ticket_ref = models.UUIDField(null=True, blank=True)

    # Consent / transparency: the tenant must know an operator is assisting.
    requires_consent = models.BooleanField(default=True)
    consent_granted_at = models.DateTimeField(null=True, blank=True)
    consent_granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="remote_support_consents",
    )

    # Whether the operator escalated to acting-as (assist_dock impersonation).
    impersonation_used = models.BooleanField(default=False)

    # Diagnostics snapshot attached to the session (P3); JSON-serialisable only.
    diagnostics = models.JSONField(default=dict, blank=True)

    summary = models.TextField(blank=True, help_text="End-of-session summary.")
    ended_reason = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_remotesupportsession"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["operator", "status"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"support:{self.school_id}:{self.status}"

    @property
    def is_open(self) -> bool:
        return self.status in self.OPEN_STATUSES

    @property
    def consent_satisfied(self) -> bool:
        """True when consent isn't required, or it has been granted."""
        return (not self.requires_consent) or self.consent_granted_at is not None

    def can_go_active(self) -> bool:
        """A session may become ACTIVE only once accepted and consent is met."""
        return (
            self.status in (self.Status.ACCEPTED, self.Status.ACTIVE)
            and self.consent_satisfied
        )

    def mark_accepted(self, operator, *, now=None) -> None:
        now = now or timezone.now()
        self.operator = operator
        self.status = self.Status.ACCEPTED
        self.accepted_at = now

    def grant_consent(self, by_user, *, now=None) -> None:
        now = now or timezone.now()
        self.consent_granted_at = now
        self.consent_granted_by = by_user

    def mark_ended(self, *, reason="", summary="", now=None) -> None:
        now = now or timezone.now()
        self.status = self.Status.ENDED
        self.ended_at = now
        if reason:
            self.ended_reason = reason[:255]
        if summary:
            self.summary = summary

    def record_lifecycle_audit(
        self, *, actor, action, reason, ip=None, user_agent=""
    ) -> None:
        """Append an AuditLog row for a session transition. Best-effort.

        Mirrors OperatorTenantAssignment.record_lifecycle_audit so every
        remote-support transition (request/accept/consent/active/end/decline)
        lands in the same audit surface. Never raises into the caller.
        """
        try:
            from apps.compliance.models_audit import AuditLog

            AuditLog.objects.create(
                user=actor if getattr(actor, "pk", None) else None,
                ip_address=ip,
                user_agent=(user_agent or "")[:500],
                action=action,
                model_name="RemoteSupportSession",
                object_id=str(self.pk or ""),
                object_repr=str(self)[:500],
                app_label="platform_runtime",
                sensitivity=AuditLog.Sensitivity.HIGH,
                new_values={
                    "school_id": str(self.school_id),
                    "operator_id": self.operator_id,
                    "requested_by_id": self.requested_by_id,
                    "status": self.status,
                    "channel": self.channel,
                    "impersonation_used": self.impersonation_used,
                },
                reason=str(reason)[:255],
            )
        except Exception:  # noqa: BLE001 — audit is best-effort, never breaks the flow
            logger.warning(
                "RemoteSupportSession lifecycle audit failed", exc_info=True
            )


class OperatorIntent(models.Model):
    """Reverse channel (cloud -> tenant): an operator action that WAITS.

    The platform's offline queue only flows tenant -> cloud, so a cloud operator
    cannot reach an offline/edge school in real time. An OperatorIntent is
    queued cloud-side; the tenant browser / edge hub polls
    ``operator-intents/pending/`` on (re)connect, applies it, and acknowledges.
    This is how remote support survives a connectivity gap. Lives in the public
    schema so operators queue from /super/ and any tenant origin can poll it.
    """

    class Kind(models.TextChoices):
        MESSAGE = "message", "Message to tenant"
        CONFIG_REFRESH = "config_refresh", "Tenant should re-pull config"
        DIAGNOSTIC_REQUEST = "diagnostic_request", "Tenant should upload diagnostics"
        SUPPORT_NOTE = "support_note", "Support note"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DELIVERED = "delivered", "Delivered (tenant fetched)"
        ACKNOWLEDGED = "acknowledged", "Acknowledged"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    LIVE_STATUSES = (Status.PENDING, Status.DELIVERED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="operator_intents",
    )
    session = models.ForeignKey(
        "platform_runtime.RemoteSupportSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_intents",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_intents_created",
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    payload = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    ack_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_operatorintent"
        ordering = ["created_at"]  # FIFO delivery
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"intent:{self.school_id}:{self.kind}:{self.status}"

    def is_live(self, *, now=None) -> bool:
        now = now or timezone.now()
        if self.status not in self.LIVE_STATUSES:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    def mark_delivered(self, *, now=None) -> None:
        now = now or timezone.now()
        if self.status == self.Status.PENDING:
            self.status = self.Status.DELIVERED
            self.delivered_at = now

    def mark_acknowledged(self, *, note="", now=None) -> None:
        now = now or timezone.now()
        self.status = self.Status.ACKNOWLEDGED
        self.acknowledged_at = now
        if note:
            self.ack_note = note[:255]


class TenantConnectivityHeartbeat(models.Model):
    """Edge/tenant phone-home so operators can SEE whether a school is online.

    The tenant browser or edge hub upserts this on a schedule. Operators read
    ``is_online`` to know if a school is reachable for live support or only for
    async (queued) support. One row per school.
    """

    school = models.OneToOneField(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="connectivity_heartbeat",
    )
    last_seen_at = models.DateTimeField(db_index=True)
    profile = models.CharField(max_length=16, blank=True)  # online/edge/hybrid
    app_version = models.CharField(max_length=64, blank=True)
    pending_sync = models.PositiveIntegerField(default=0)
    meta = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Default freshness window: a school not seen within this is "offline".
    ONLINE_THRESHOLD_SECONDS = 600  # magic-number-allow: heartbeat-online-freshness-window-seconds

    class Meta:
        app_label = "platform_runtime"
        db_table = "platform_runtime_tenantheartbeat"

    def __str__(self) -> str:
        return f"heartbeat:{self.school_id}"

    def is_online(self, *, now=None, threshold_seconds=None) -> bool:
        if self.last_seen_at is None:
            return False
        now = now or timezone.now()
        threshold = threshold_seconds or self.ONLINE_THRESHOLD_SECONDS
        return (now - self.last_seen_at).total_seconds() <= threshold
