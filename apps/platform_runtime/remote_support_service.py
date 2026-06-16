"""Remote Support P2 — the online support loop (service layer).

Orchestrates the RemoteSupportSession lifecycle with guard checks, audit, and
tenant-facing transparency notifications:

    tenant requests help  -> request_remote_support()   (REQUESTED)
    operator accepts      -> accept_remote_support()     (ACCEPTED + notify tenant)
    tenant grants consent -> record_consent()            (consent stamped)
    operator begins       -> activate_remote_support()   (ACTIVE, needs consent)
    operator finishes     -> end_remote_support()        (ENDED + summary + notify)
    either declines/cancels -> decline/cancel

Every transition is audited via RemoteSupportSession.record_lifecycle_audit.
Tenant notifications use the platform Notification model (TENANT_APPS) and are
best-effort + schema-safe: they only succeed in a tenant request context, and a
failure (e.g. called from the public schema) is swallowed — the session state is
the source of truth and the consent banner renders from it regardless.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.compliance.models_audit import AuditLog
from apps.platform_runtime.models_remote_support import RemoteSupportSession
from apps.platform_runtime.remote_support_access import operator_can_remote_support

logger = logging.getLogger(__name__)

_NOTIFY_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def _notify_tenant_user(recipient, *, title, message, link="", actor=None) -> None:
    """Best-effort tenant-facing notification (schema-safe no-op off-tenant)."""
    if recipient is None or getattr(recipient, "pk", None) is None:
        return
    try:
        from apps.finance.models import Notification

        Notification.objects.create(
            recipient=recipient,
            created_by=actor if getattr(actor, "pk", None) else None,
            title=title[:200],
            message=message,
            link=(link or "")[:256],
            severity=Notification.Severity.INFO,
        )
    except _NOTIFY_ERRORS:
        # Off-tenant schema or notifications unavailable — the session state and
        # the consent banner remain the source of truth.
        logger.info("remote-support tenant notify skipped", exc_info=True)


def _activate_if_ready(session, *, actor) -> bool:
    """Promote an ACCEPTED + consent-satisfied session to ACTIVE.

    The online handshake is request -> accept -> consent. Once both an operator
    has accepted AND consent is satisfied, the session is cleared to go ACTIVE —
    there is no separate "begin" click. Called from both accept (consent may be
    pre-satisfied / not required) and consent (the common path), so ACTIVE is
    reachable regardless of ordering. No-op unless currently ACCEPTED.
    """
    if (
        session.status == RemoteSupportSession.Status.ACCEPTED
        and session.consent_satisfied
    ):
        session.status = RemoteSupportSession.Status.ACTIVE
        session.save(update_fields=["status", "updated_at"])
        session.record_lifecycle_audit(
            actor=actor,
            action=AuditLog.Action.UPDATE,
            reason="Remote support session activated (consent satisfied)",
        )
        return True
    return False


def request_remote_support(
    *, school, requested_by, reason="", channel=None, initiator=None
) -> RemoteSupportSession:
    """Tenant (or operator) opens a remote-support request."""
    channel = channel or RemoteSupportSession.Channel.ONLINE
    initiator = initiator or RemoteSupportSession.Initiator.TENANT
    session = RemoteSupportSession.objects.create(
        school=school,
        requested_by=requested_by,
        initiator=initiator,
        channel=channel,
        reason=(reason or "")[:500],
        status=RemoteSupportSession.Status.REQUESTED,
    )
    session.record_lifecycle_audit(
        actor=requested_by,
        action=AuditLog.Action.CREATE,
        reason="Remote support requested",
    )
    return session


def accept_remote_support(
    *, session, operator, ip=None, user_agent=""
) -> RemoteSupportSession:
    """Operator accepts a request. Enforces the remote-support gate."""
    if not operator_can_remote_support(operator, session.school):
        raise PermissionDenied(
            "You are not authorized to provide remote support for this tenant."
        )
    if not session.is_open:
        raise PermissionDenied("This support session is no longer open.")
    session.mark_accepted(operator)
    session.save(
        update_fields=["operator", "status", "accepted_at", "updated_at"]
    )
    session.record_lifecycle_audit(
        actor=operator,
        action=AuditLog.Action.APPROVE,
        reason="Remote support accepted by operator",
        ip=ip,
        user_agent=user_agent,
    )
    _notify_tenant_user(
        session.requested_by,
        title="An operator is ready to help",
        message=(
            "A RunMyCampus operator accepted your support request and will "
            "assist you. You will be asked to confirm consent before they begin."
        ),
        actor=operator,
    )
    # When consent isn't required (or was pre-granted), accepting clears the
    # session to ACTIVE immediately; otherwise it waits for record_consent.
    _activate_if_ready(session, actor=operator)
    return session


def record_consent(*, session, by_user) -> RemoteSupportSession:
    """Tenant grants consent for the operator to assist."""
    session.grant_consent(by_user)
    session.save(
        update_fields=["consent_granted_at", "consent_granted_by", "updated_at"]
    )
    session.record_lifecycle_audit(
        actor=by_user,
        action=AuditLog.Action.APPROVE,
        reason="Tenant granted remote-support consent",
    )
    # Consent is the final gate of the handshake: if an operator already
    # accepted, granting consent promotes the session to ACTIVE.
    _activate_if_ready(session, actor=by_user)
    return session


def activate_remote_support(*, session, operator) -> RemoteSupportSession:
    """Operator begins assisting. Requires accepted + consent satisfied."""
    if not operator_can_remote_support(operator, session.school):
        raise PermissionDenied(
            "You are not authorized to provide remote support for this tenant."
        )
    if not session.can_go_active():
        raise PermissionDenied(
            "Cannot begin: the session needs acceptance and tenant consent."
        )
    session.status = RemoteSupportSession.Status.ACTIVE
    session.save(update_fields=["status", "updated_at"])
    session.record_lifecycle_audit(
        actor=operator,
        action=AuditLog.Action.UPDATE,
        reason="Remote support session activated",
    )
    return session


def end_remote_support(
    *, session, actor, reason="", summary=""
) -> RemoteSupportSession:
    """End the session with an audited summary; notify the tenant."""
    session.mark_ended(reason=reason, summary=summary)
    session.save(
        update_fields=["status", "ended_at", "ended_reason", "summary", "updated_at"]
    )
    session.record_lifecycle_audit(
        actor=actor,
        action=AuditLog.Action.UPDATE,
        reason="Remote support session ended",
    )
    _notify_tenant_user(
        session.requested_by,
        title="Support session ended",
        message=(
            "Your remote-support session has ended."
            + (f" Summary: {summary}" if summary else "")
        ),
        actor=actor,
    )
    return session


def _close(session, *, actor, status, reason) -> RemoteSupportSession:
    session.status = status
    session.ended_at = timezone.now()
    session.ended_reason = reason[:255]
    session.save(update_fields=["status", "ended_at", "ended_reason", "updated_at"])
    session.record_lifecycle_audit(
        actor=actor, action=AuditLog.Action.UPDATE, reason=reason
    )
    return session


def decline_remote_support(*, session, actor, reason="Declined") -> RemoteSupportSession:
    return _close(
        session,
        actor=actor,
        status=RemoteSupportSession.Status.DECLINED,
        reason=reason or "Remote support declined",
    )


def cancel_remote_support(*, session, actor, reason="Cancelled") -> RemoteSupportSession:
    return _close(
        session,
        actor=actor,
        status=RemoteSupportSession.Status.CANCELLED,
        reason=reason or "Remote support cancelled",
    )
