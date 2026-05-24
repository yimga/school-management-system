"""Localized dispute/refund copy helpers (SFDP 1468)."""

from __future__ import annotations

from django.utils.translation import gettext_lazy as _

DISPUTE_STATUS_COPY = {
    "open": _("Dispute under review"),
    "won": _("Dispute resolved in your favor"),
    "lost": _("Dispute closed — contact the bursar"),
    "pending": _("Refund processing"),
    "succeeded": _("Refund completed"),
    "failed": _("Refund could not be completed"),
}


def parent_dispute_message(status: str) -> str:
    return str(DISPUTE_STATUS_COPY.get(str(status).lower(), _("Payment adjustment in progress")))
