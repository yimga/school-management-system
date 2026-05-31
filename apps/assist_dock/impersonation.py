"""v4.00.97 Wave G2 — real impersonation flow.

Dual-control grant + session swap + audit trail. The operator-facing
threat model:

  * Only SUPERADMIN can request OR approve a grant.
  * A grant requires a second SUPERADMIN's approval (request + approve
    are two distinct user actions; ``approver != grantor``).
  * A grant is single-use, scoped to one target user, time-limited
    (default 30 min from approval), and consumed at session-start.
  * The impersonator's REAL user id is stashed in the session under
    ``_impersonator_id``; an ``AssistDockImpersonationMiddleware`` later
    in the chain injects an unmistakable banner on every page until the
    operator clicks "End impersonation" (or the session is dropped).
  * Every state transition (request / approve / start / stop / expire)
    writes an ``ImpersonationAuditEvent`` row — append-only, never
    deleted, FERPA-retention-aligned.

What this module does NOT do (intentional residuals):

  * RBAC restore — the impersonator inherits the target's full perms
    for the duration. Add app-specific guards in views that should
    REFUSE impersonation (e.g. "change-password" must check
    ``request.session.get('_impersonator_id') is None``).
  * Action-level audit — only the session start/stop is logged; mid-
    session actions log under the impersonated user's pk via the normal
    request log. Add an ``ImpersonationActionAudit`` in a later wave
    when the operator needs per-click receipts.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


GRANT_DEFAULT_TTL_SECONDS = 30 * 60       # 30 min from approval
GRANT_MAX_TTL_SECONDS = 4 * 60 * 60       # 4 h absolute ceiling
GRANT_REASON_MAX_LEN = 280                # tweet-length reason
SESSION_KEY_IMPERSONATOR = "_assist_dock_impersonator_id"
SESSION_KEY_GRANT_ID = "_assist_dock_impersonation_grant_id"
SESSION_KEY_STARTED_AT = "_assist_dock_impersonation_started_at"


class ImpersonationGrantStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    CONSUMED = "consumed", "Consumed"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"


class ImpersonationAuditEventType(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    STARTED = "started", "Started"
    STOPPED = "stopped", "Stopped"
    EXPIRED_AT_START = "expired_at_start", "Expired before start"
    REVOKED = "revoked", "Revoked"
    DENIED_BY_RBAC = "denied_by_rbac", "Denied by RBAC"


class ImpersonationGrant(models.Model):
    """One operator-issued grant authorizing a second operator to impersonate.

    Status FSM: ``REQUESTED → APPROVED → CONSUMED`` (happy path); any
    state may transition to ``EXPIRED`` or ``REVOKED``.
    """

    grantor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_impersonation_grants_requested",
        help_text="Operator who requested the grant.",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assist_dock_impersonation_grants_approved",
        help_text="Operator who approved (must differ from grantor).",
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_impersonation_grants_received",
        help_text="User who will be impersonated when this grant is consumed.",
    )
    reason = models.CharField(max_length=GRANT_REASON_MAX_LEN)
    status = models.CharField(
        max_length=16,
        choices=ImpersonationGrantStatus.choices,
        default=ImpersonationGrantStatus.REQUESTED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Assist dock impersonation grant"
        verbose_name_plural = "Assist dock impersonation grants"
        indexes = [
            models.Index(
                fields=("status", "expires_at"),
                name="ad_imp_grant_status_idx",
            ),
            models.Index(
                fields=("grantor", "created_at"),
                name="ad_imp_grant_grantor_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin only
        return f"ImpersonationGrant({self.pk}, {self.status})"

    def is_expired(self, *, now=None) -> bool:
        now = now or timezone.now()
        return self.expires_at <= now

    def is_consumable(self, *, now=None) -> bool:
        return (
            self.status == ImpersonationGrantStatus.APPROVED
            and not self.is_expired(now=now)
        )


class ImpersonationSession(models.Model):
    """One concrete impersonation session created by consuming a grant."""

    grant = models.ForeignKey(
        ImpersonationGrant,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_impersonation_sessions_run",
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assist_dock_impersonation_sessions_subject",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    ended_reason = models.CharField(max_length=64, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        verbose_name = "Assist dock impersonation session"
        verbose_name_plural = "Assist dock impersonation sessions"
        indexes = [
            models.Index(
                fields=("operator", "started_at"),
                name="ad_imp_sess_op_idx",
            ),
            models.Index(
                fields=("target", "started_at"),
                name="ad_imp_sess_target_idx",
            ),
        ]


class ImpersonationAuditEvent(models.Model):
    """Append-only event log for every impersonation state transition."""

    grant = models.ForeignKey(
        ImpersonationGrant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    session = models.ForeignKey(
        ImpersonationSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assist_dock_impersonation_audit_events",
    )
    event_type = models.CharField(
        max_length=24,
        choices=ImpersonationAuditEventType.choices,
    )
    notes = models.CharField(max_length=200, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Assist dock impersonation audit event"
        verbose_name_plural = "Assist dock impersonation audit events"
        indexes = [
            models.Index(
                fields=("grant", "created_at"),
                name="ad_imp_audit_grant_idx",
            ),
            models.Index(
                fields=("actor", "created_at"),
                name="ad_imp_audit_actor_idx",
            ),
        ]


# --- service-layer helpers (pure functions where possible) -----------------


def clamp_ttl_seconds(raw) -> int:
    try:
        ttl = int(raw)
    except (TypeError, ValueError):
        return GRANT_DEFAULT_TTL_SECONDS
    if ttl <= 0:
        return GRANT_DEFAULT_TTL_SECONDS
    if ttl > GRANT_MAX_TTL_SECONDS:
        return GRANT_MAX_TTL_SECONDS
    return ttl


def is_super(user) -> bool:
    """SUPERADMIN-or-superuser check, defensive on attribute-shape variance."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    # Project also has a ``primary_role`` / ``role`` enum; SUPERADMIN wins.
    for attr in ("primary_role", "active_role", "role"):
        value = getattr(user, attr, "") or ""
        if str(value).upper() == "SUPERADMIN":
            return True
    return False


def request_grant(
    *,
    grantor,
    target_user_id: int,
    reason: str,
    ttl_seconds: int | None = None,
) -> tuple[str, ImpersonationGrant | None]:
    """Create a new REQUESTED grant.

    Returns ``("ok", grant)`` on success, or ``("<error_code>", None)``.
    """
    if not is_super(grantor):
        return ("not_super", None)
    if grantor.pk == target_user_id:
        return ("self_target", None)
    if not reason or not reason.strip():
        return ("missing_reason", None)
    reason = reason.strip()[:GRANT_REASON_MAX_LEN]
    try:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        target = User.objects.filter(pk=target_user_id).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("request_grant: user lookup failed: %s", exc)
        return ("lookup_failed", None)
    if target is None:
        return ("target_not_found", None)
    if not getattr(target, "is_active", True):
        return ("target_inactive", None)
    ttl = clamp_ttl_seconds(ttl_seconds)
    expires_at = timezone.now() + timedelta(seconds=ttl)
    # tenant-isolation-allow: assist-dock-impersonation-grant-create-public-schema-shared
    grant = ImpersonationGrant.objects.create(
        grantor=grantor,
        target=target,
        reason=reason,
        expires_at=expires_at,
    )
    record_audit_event(
        grant=grant,
        actor=grantor,
        event_type=ImpersonationAuditEventType.REQUESTED,
        notes=f"ttl={ttl}",
    )
    return ("ok", grant)


def approve_grant(
    *, approver, grant_id: int
) -> tuple[str, ImpersonationGrant | None]:
    """Promote a REQUESTED grant to APPROVED. Approver MUST NOT be grantor."""
    if not is_super(approver):
        return ("not_super", None)
    try:
        # tenant-isolation-allow: assist-dock-impersonation-grant-approve-public-schema-shared
        grant = ImpersonationGrant.objects.filter(pk=grant_id).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("approve_grant: lookup failed: %s", exc)
        return ("lookup_failed", None)
    if grant is None:
        return ("grant_not_found", None)
    if grant.status != ImpersonationGrantStatus.REQUESTED:
        return ("wrong_state", None)
    if grant.is_expired():
        grant.status = ImpersonationGrantStatus.EXPIRED
        grant.save(update_fields=["status"])
        record_audit_event(
            grant=grant,
            actor=approver,
            event_type=ImpersonationAuditEventType.EXPIRED_AT_START,
            notes="approve_after_expiry",
        )
        return ("expired", None)
    if grant.grantor_id == approver.pk:
        record_audit_event(
            grant=grant,
            actor=approver,
            event_type=ImpersonationAuditEventType.DENIED_BY_RBAC,
            notes="self_approval_blocked",
        )
        return ("dual_control_violation", None)
    grant.approver = approver
    grant.approved_at = timezone.now()
    grant.status = ImpersonationGrantStatus.APPROVED
    grant.save(update_fields=["approver", "approved_at", "status"])
    record_audit_event(
        grant=grant,
        actor=approver,
        event_type=ImpersonationAuditEventType.APPROVED,
    )
    return ("ok", grant)


def revoke_grant(
    *, actor, grant_id: int
) -> tuple[str, ImpersonationGrant | None]:
    """Revoke a grant (any SUPERADMIN, any state besides CONSUMED)."""
    if not is_super(actor):
        return ("not_super", None)
    try:
        grant = ImpersonationGrant.objects.filter(pk=grant_id).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("revoke_grant: lookup failed: %s", exc)
        return ("lookup_failed", None)
    if grant is None:
        return ("grant_not_found", None)
    if grant.status == ImpersonationGrantStatus.CONSUMED:
        return ("already_consumed", None)
    grant.status = ImpersonationGrantStatus.REVOKED
    grant.save(update_fields=["status"])
    record_audit_event(
        grant=grant,
        actor=actor,
        event_type=ImpersonationAuditEventType.REVOKED,
    )
    return ("ok", grant)


def record_audit_event(
    *,
    grant=None,
    session=None,
    actor=None,
    event_type: str,
    notes: str = "",
) -> ImpersonationAuditEvent | None:
    """Append an audit event. Best-effort — failure logs WARNING + returns None."""
    try:
        # tenant-isolation-allow: assist-dock-impersonation-audit-create-public-schema-shared
        return ImpersonationAuditEvent.objects.create(
            grant=grant,
            session=session,
            actor=actor,
            event_type=event_type,
            notes=(notes or "")[:200],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("impersonation audit write failed: %s", exc)
        return None


def start_session_from_grant(
    *,
    operator,
    grant_id: int,
    request_session,
    ip: str | None = None,
    user_agent: str = "",
) -> tuple[str, ImpersonationSession | None]:
    """Consume an APPROVED grant; install impersonation in the session."""
    if not is_super(operator):
        return ("not_super", None)
    try:
        grant = ImpersonationGrant.objects.filter(pk=grant_id).first()
    except Exception as exc:  # noqa: BLE001
        logger.debug("start_session: lookup failed: %s", exc)
        return ("lookup_failed", None)
    if grant is None:
        return ("grant_not_found", None)
    if grant.approver_id != operator.pk and grant.grantor_id != operator.pk:
        # Only the grantor (who requested it) or the approver may start it.
        return ("not_assignee", None)
    if not grant.is_consumable():
        if grant.is_expired() and grant.status != ImpersonationGrantStatus.EXPIRED:
            grant.status = ImpersonationGrantStatus.EXPIRED
            grant.save(update_fields=["status"])
            record_audit_event(
                grant=grant,
                actor=operator,
                event_type=ImpersonationAuditEventType.EXPIRED_AT_START,
            )
            return ("expired", None)
        return ("wrong_state", None)
    grant.consumed_at = timezone.now()
    grant.status = ImpersonationGrantStatus.CONSUMED
    grant.save(update_fields=["consumed_at", "status"])
    # tenant-isolation-allow: assist-dock-impersonation-session-create-public-schema-shared
    session = ImpersonationSession.objects.create(
        grant=grant,
        operator=operator,
        target=grant.target,
        ip=ip or None,
        user_agent=(user_agent or "")[:256],
    )
    if request_session is not None:
        request_session[SESSION_KEY_IMPERSONATOR] = operator.pk
        request_session[SESSION_KEY_GRANT_ID] = grant.pk
        request_session[SESSION_KEY_STARTED_AT] = (
            session.started_at.isoformat() if session.started_at else ""
        )
    record_audit_event(
        grant=grant,
        session=session,
        actor=operator,
        event_type=ImpersonationAuditEventType.STARTED,
    )
    return ("ok", session)


def stop_session(*, operator, request_session) -> tuple[str, dict]:
    """End the active impersonation in ``request_session`` (idempotent)."""
    if request_session is None:
        return ("no_session", {})
    grant_id = request_session.get(SESSION_KEY_GRANT_ID)
    impersonator_id = request_session.get(SESSION_KEY_IMPERSONATOR)
    if not grant_id and not impersonator_id:
        return ("no_session", {})
    session = None
    try:
        if grant_id:
            session = (
                ImpersonationSession.objects.filter(grant_id=grant_id, ended_at__isnull=True)
                .order_by("-started_at")
                .first()
            )
    except Exception as exc:  # noqa: BLE001
        logger.debug("stop_session: lookup failed: %s", exc)
        session = None
    if session is not None:
        session.ended_at = timezone.now()
        session.ended_reason = "manual_stop"
        session.save(update_fields=["ended_at", "ended_reason"])
        record_audit_event(
            grant=session.grant,
            session=session,
            actor=operator,
            event_type=ImpersonationAuditEventType.STOPPED,
        )
    for key in (
        SESSION_KEY_IMPERSONATOR,
        SESSION_KEY_GRANT_ID,
        SESSION_KEY_STARTED_AT,
    ):
        request_session.pop(key, None)
    return ("ok", {"session_id": session.pk if session else None})


def session_banner_context(request) -> dict:
    """Read-only banner payload for the impersonation banner middleware."""
    try:
        sess = getattr(request, "session", None)
    except Exception:  # noqa: BLE001
        return {}
    if not sess:
        return {}
    grant_id = sess.get(SESSION_KEY_GRANT_ID)
    impersonator_id = sess.get(SESSION_KEY_IMPERSONATOR)
    if not grant_id or not impersonator_id:
        return {}
    return {
        "active": True,
        "grant_id": grant_id,
        "impersonator_id": impersonator_id,
        "started_at_iso": sess.get(SESSION_KEY_STARTED_AT, ""),
    }
