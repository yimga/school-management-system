"""Locale-aware parent/operator copy for refund and dispute lifecycle (SFDP 1468)."""

from __future__ import annotations

from typing import Any, Literal

from django.utils.translation import gettext_lazy as _

Audience = Literal["parent", "operator"]

PARENT_STATUS_COPY: dict[str, str] = {
    "OPEN": _("We received your dispute and will review it shortly."),
    "UNDER_REVIEW": _("Our finance team is reviewing your dispute."),
    "RESOLVED_REFUND": _("Your dispute was resolved and a refund was issued."),
    "RESOLVED_NO_REFUND": _("Your dispute was reviewed and closed without a refund."),
    "CLOSED": _("This dispute is closed."),
}

OPERATOR_STATUS_COPY: dict[str, str] = {
    "OPEN": _("New dispute — assign reviewer and gather payment evidence."),
    "UNDER_REVIEW": _("Dispute under review — confirm ledger and PSP status."),
    "RESOLVED_REFUND": _("Refund issued — reconcile ledger and notify parent."),
    "RESOLVED_NO_REFUND": _("Closed without refund — document rationale for audit."),
    "CLOSED": _("Dispute closed — retention window applies per policy."),
}

REFUND_PARENT_COPY: dict[str, str] = {
    "pending": _("Refund requested — processing may take a few business days."),
    "succeeded": _("Refund completed — check your statement for the credit."),
    "failed": _("Refund could not be completed — contact the school bursar."),
}

REFUND_OPERATOR_COPY: dict[str, str] = {
    "pending": _("Refund pending — verify PSP webhook and ledger hold."),
    "succeeded": _("Refund succeeded — confirm settlement and close ticket."),
    "failed": _("Refund failed — escalate to PSP support with evidence."),
}


def dispute_copy_for_status(
    status: str,
    *,
    audience: Audience = "parent",
    profile: dict[str, Any] | None = None,
) -> str:
    """Return human-readable dispute status copy for parents or operators."""
    _ = profile  # reserved for profile-specific vocabulary (rail/locale hints)
    table = PARENT_STATUS_COPY if audience == "parent" else OPERATOR_STATUS_COPY
    key = str(status or "OPEN").upper()
    return str(table.get(key, table["OPEN"]))


def refund_copy_for_status(
    status: str,
    *,
    audience: Audience = "parent",
    profile: dict[str, Any] | None = None,
) -> str:
    """Return human-readable refund status copy for parents or operators."""
    _ = profile
    table = REFUND_PARENT_COPY if audience == "parent" else REFUND_OPERATOR_COPY
    key = str(status or "pending").lower()
    return str(table.get(key, table["pending"]))
