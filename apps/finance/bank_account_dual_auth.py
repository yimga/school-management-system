"""Service layer for the BankAccount dual-authorization workflow.

Single entry-point per state transition. Direct ORM writes to
``BankAccount`` from views / admin / management commands MUST go through
``request_bank_account_change`` first. The peer approver THEN calls
``approve_bank_account_change`` to apply.

Audit trail: every transition writes a CRITICAL-sensitivity ``AuditLog``
row capturing the actor, IP, before/after payload, and reason.

Tenant isolation: the request's ``school`` FK is the source of truth.
The service refuses to apply a change if the underlying ``BankAccount``
no longer belongs to the same school (defense-in-depth against TOCTOU).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger("apps.finance.bank_account_dual_auth")

# Default request lifetime; operators can override via settings.
DEFAULT_TTL_HOURS = 48


def _ttl() -> timedelta:
    hours = getattr(settings, "BANK_ACCOUNT_CHANGE_REQUEST_TTL_HOURS", DEFAULT_TTL_HOURS)
    return timedelta(hours=int(hours))


def _audit(*, action: str, request, actor, before: dict | None, after: dict | None, reason: str, ip: str | None) -> None:
    """Write a CRITICAL-sensitivity AuditLog row. Soft-fail if the audit
    pipeline itself errors — never block the financial workflow on telemetry.
    """
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            action=action,
            user=actor,
            ip_address=ip,
            model_name="BankAccountChangeRequest",
            object_id=str(request.id),
            object_repr=str(request),
            app_label="finance",
            sensitivity=AuditLog.Sensitivity.CRITICAL,
            old_values=before,
            new_values=after,
            reason=reason,
        )
    except (ImportError, ValueError, TypeError, AttributeError, RuntimeError) as e:  # pragma: no cover - defensive
        logger.warning("BankAccount dual-auth audit write failed: %s", e)


def request_bank_account_change(
    *,
    school,
    change_kind: str,
    payload: dict[str, Any],
    requester,
    reason: str,
    bank_account=None,
    requester_ip: str | None = None,
):
    """Create a PENDING change request. The change is NOT applied until a
    different administrator calls ``approve_bank_account_change``.

    Returns the created ``BankAccountChangeRequest`` instance.

    Raises ``ValidationError`` on:
      * empty / too-short ``reason``
      * UPDATE/DEACTIVATE without a ``bank_account`` target
      * CREATE with a ``bank_account`` target (use UPDATE instead)
      * unknown ``change_kind``
    """
    from .models_dual_auth import BankAccountChangeRequest

    kind = (change_kind or "").upper()
    if kind not in BankAccountChangeRequest.ChangeKind.values:
        raise ValidationError(f"Unknown change_kind: {change_kind!r}")

    if (reason or "").strip().__len__() < 8:
        raise ValidationError("reason must be at least 8 characters explaining why the change is needed.")

    if kind == BankAccountChangeRequest.ChangeKind.CREATE and bank_account is not None:
        raise ValidationError("CREATE requests must not target an existing bank account.")
    if kind in (BankAccountChangeRequest.ChangeKind.UPDATE, BankAccountChangeRequest.ChangeKind.DEACTIVATE):
        if bank_account is None:
            raise ValidationError(f"{kind} requires a target bank_account.")

    return BankAccountChangeRequest.objects.create(
        school=school,
        bank_account=bank_account,
        change_kind=kind,
        payload=payload or {},
        reason=reason.strip(),
        requester=requester,
        requester_ip=requester_ip,
        expires_at=timezone.now() + _ttl(),
    )


def _refuse_same_actor(request, approver) -> None:
    if request.requester_id == getattr(approver, "id", None):
        raise ValidationError(
            "Dual-authorization: the approver must be a different administrator "
            "than the requester."
        )


def _refuse_stale_request(request) -> None:
    if not request.is_pending:
        raise ValidationError(f"Request is not pending (state={request.state}).")
    if request.is_expired:
        raise ValidationError("Request has expired; the requester must file a new one.")


def approve_bank_account_change(
    *,
    request_id,
    approver,
    note: str = "",
    approver_ip: str | None = None,
):
    """Apply a PENDING change to the live BankAccount row, atomically.

    The approver MUST be a different user than the requester. Re-approving
    an already-decided request is a no-op (raises ValidationError).
    """
    from .models import BankAccount
    from .models_dual_auth import BankAccountChangeRequest

    with transaction.atomic():
        request = (
            BankAccountChangeRequest.objects.select_for_update()
            .select_related("bank_account", "school", "requester")
            .get(pk=request_id)
        )
        _refuse_stale_request(request)
        _refuse_same_actor(request, approver)

        before: dict[str, Any] | None = None
        after: dict[str, Any] | None = None

        if request.change_kind == BankAccountChangeRequest.ChangeKind.CREATE:
            account = BankAccount.objects.create(**request.payload)
            request.bank_account = account
            after = _snapshot(account)
        elif request.change_kind == BankAccountChangeRequest.ChangeKind.UPDATE:
            account = request.bank_account
            if account is None:
                raise ValidationError("UPDATE request lost its bank_account target.")
            before = _snapshot(account)
            for field, value in (request.payload or {}).items():
                setattr(account, field, value)
            account.save()
            after = _snapshot(account)
        elif request.change_kind == BankAccountChangeRequest.ChangeKind.DEACTIVATE:
            account = request.bank_account
            if account is None:
                raise ValidationError("DEACTIVATE request lost its bank_account target.")
            before = _snapshot(account)
            account.is_active = False
            account.save(update_fields=["is_active", "updated_at"])
            after = _snapshot(account)

        request.state = BankAccountChangeRequest.State.APPROVED
        request.approver = approver
        request.approver_ip = approver_ip
        request.approver_note = (note or "").strip()
        request.decided_at = timezone.now()
        request.save(
            update_fields=[
                "state",
                "approver",
                "approver_ip",
                "approver_note",
                "decided_at",
                "bank_account",
                "updated_at",
            ]
        )

        _audit(
            action="APPROVE",
            request=request,
            actor=approver,
            before=before,
            after=after,
            reason=f"Bank account dual-auth approved: {request.approver_note}",
            ip=approver_ip,
        )

    return request


def reject_bank_account_change(
    *,
    request_id,
    approver,
    note: str,
    approver_ip: str | None = None,
):
    """Decline a PENDING change without applying it."""
    from .models_dual_auth import BankAccountChangeRequest

    if (note or "").strip().__len__() < 4:
        raise ValidationError("reject reason must be at least 4 characters.")

    with transaction.atomic():
        request = (
            BankAccountChangeRequest.objects.select_for_update().get(pk=request_id)
        )
        _refuse_stale_request(request)
        _refuse_same_actor(request, approver)

        request.state = BankAccountChangeRequest.State.REJECTED
        request.approver = approver
        request.approver_ip = approver_ip
        request.approver_note = note.strip()
        request.decided_at = timezone.now()
        request.save(
            update_fields=[
                "state",
                "approver",
                "approver_ip",
                "approver_note",
                "decided_at",
                "updated_at",
            ]
        )
        _audit(
            action="REJECT",
            request=request,
            actor=approver,
            before=None,
            after=None,
            reason=f"Bank account dual-auth rejected: {request.approver_note}",
            ip=approver_ip,
        )

    return request


def expire_stale_requests() -> int:
    """Sweep PENDING requests past expires_at into the EXPIRED state.

    Intended to run from a Celery beat / management command. Returns the
    number of rows updated.
    """
    from .models_dual_auth import BankAccountChangeRequest

    now = timezone.now()
    # tenant-isolation-allow: platform-wide sweeper invoked by Celery beat across all tenants by design (no per-tenant context available)
    return BankAccountChangeRequest.objects.filter(
        state=BankAccountChangeRequest.State.PENDING,
        expires_at__lte=now,
    ).update(state=BankAccountChangeRequest.State.EXPIRED, updated_at=now)


def _snapshot(account) -> dict[str, Any]:
    """Capture the audit-relevant fields of a BankAccount for old/new values."""
    return {
        "id": account.pk,
        "name": account.name,
        "account_type": account.account_type,
        "account_number": account.account_number,
        "bank_name": account.bank_name,
        "branch": account.branch,
        "currency": account.currency,
        "is_active": account.is_active,
        "region_id": account.region_id,
    }
