"""Dual-authorization (M-of-N) state machine for high-risk financial routing changes.

The fraud vector this closes: a single compromised admin account can rewrite
a school's bank account / mobile-money number / payout destination, and
parents who pay tuition during the window route money to the attacker.

Pattern: any modification to a ``BankAccount`` (create / update / deactivate)
is filed as a ``BankAccountChangeRequest`` in the ``PENDING`` state. A
**different** authenticated administrator (the ``approver``) must explicitly
approve it before the change is applied to the live ``BankAccount`` row.
Rejected or expired requests never touch the live account.

The mechanism mirrors the existing ``School.impersonation_dual_control``
four-eyes flow (``apps/schools/super_views_impersonation.py``) — same
"different actor" + audit-log discipline.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class BankAccountChangeRequest(models.Model):
    """Pending change to a financial routing record awaiting peer approval.

    State transitions (one-way, except APPROVED → APPLIED is implicit):
        PENDING → APPROVED   (peer approver signs off; change is applied)
        PENDING → REJECTED   (peer approver declines; change is discarded)
        PENDING → EXPIRED    (expires_at passed without decision)

    Tenant binding: ``school`` FK + the underlying ``BankAccount`` row's
    ``region.school`` chain. The change_kind=CREATE case carries the school
    explicitly because the target account does not exist yet.
    """

    class State(models.TextChoices):
        PENDING = "PENDING", "Pending second-admin approval"
        APPROVED = "APPROVED", "Approved & applied"
        REJECTED = "REJECTED", "Rejected by peer approver"
        EXPIRED = "EXPIRED", "Expired without decision"

    class ChangeKind(models.TextChoices):
        CREATE = "CREATE", "Create new bank account"
        UPDATE = "UPDATE", "Modify existing bank account"
        DEACTIVATE = "DEACTIVATE", "Deactivate bank account"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="bank_account_change_requests",
        help_text="Tenant the change targets — required for tenant isolation.",
    )
    bank_account = models.ForeignKey(
        "finance.BankAccount",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="change_requests",
        help_text="Target account; null for CREATE (account does not exist yet).",
    )
    change_kind = models.CharField(max_length=16, choices=ChangeKind.choices)
    payload = models.JSONField(
        default=dict,
        help_text=(
            "Proposed field values. For CREATE: the full account spec. "
            "For UPDATE: only the fields being changed (with their new values). "
            "For DEACTIVATE: empty (the action is implicit)."
        ),
    )
    reason = models.TextField(
        help_text="Why the requester needs this change. Mandatory."
    )

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bank_account_change_requests_filed",
        help_text="The administrator who initiated the change.",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bank_account_change_requests_decided",
        help_text="The peer administrator who approved or rejected the change.",
    )
    approver_note = models.TextField(
        blank=True,
        help_text="Approver's justification (visible in audit log).",
    )

    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.PENDING,
        db_index=True,
    )

    requester_ip = models.GenericIPAddressField(null=True, blank=True)
    approver_ip = models.GenericIPAddressField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(
        help_text="Pending requests auto-expire after this time."
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Bank account change request"
        verbose_name_plural = "Bank account change requests"
        indexes = [
            models.Index(fields=["school", "state"]),
            models.Index(fields=["state", "expires_at"]),
        ]

    def __str__(self) -> str:
        target = self.bank_account_id or "<new>"
        return f"BankAccountChangeRequest({self.change_kind} on {target}, {self.state})"

    @property
    def is_pending(self) -> bool:
        return self.state == self.State.PENDING

    @property
    def is_expired(self) -> bool:
        return self.is_pending and self.expires_at <= timezone.now()
