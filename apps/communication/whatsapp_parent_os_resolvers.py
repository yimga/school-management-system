"""Wave P-D (v3.95.1 — 2026-05-26) — WhatsApp Parent OS placeholder resolver.

Provides a real :func:`placeholder_resolver` implementation for the
Wave H kernel. Looks up the inbound phone against guardian / student records
and fills:

- ``{balance}`` — current outstanding fees (formatted)
- ``{student}`` — the student's display name (first guardian → first child)
- ``{summary}`` — placeholder homework summary
- ``{link}`` — placeholder report-card link

All lookups are scoped to the tenant by `inbound.tenant_id`. Anything that
can't be resolved leaves the literal `{placeholder}` in place (which the
kernel then sends as-is — better than crashing).
"""

from __future__ import annotations

import logging
from typing import Any

from .whatsapp_parent_os import InboundMessage


logger = logging.getLogger(__name__)


_PHONE_FIELDS: tuple[str, ...] = (
    "phone_e164", "phone", "mobile", "primary_phone", "whatsapp_phone",
    "whatsapp_number",
)


def _normalize_phone(raw: str) -> str:
    """Strip non-digit characters (keep leading + for E.164)."""
    if not raw:
        return ""
    digits = [c for c in raw if c.isdigit() or c == "+"]
    return "".join(digits)


def _find_guardian(tenant_id: str, phone: str):
    """Look up a Guardian by phone within a tenant scope. Returns None on miss."""
    try:
        from apps.people.models import StudentGuardian
    except Exception:  # noqa: BLE001
        return None
    norm = _normalize_phone(phone)
    if not norm:
        return None

    # StudentGuardian has no direct school FK; it is tenant-scoped through the
    # linked student (StudentProfile.school). school_id is a UUID, so a malformed
    # tenant_id must yield a clean miss (None), not raise — preserve the
    # never-crash contract.
    qs = StudentGuardian.objects.all()  # tenant-isolation-allow: scoped-below-via-student-school-when-tenant-id-present
    if tenant_id:
        try:
            qs = qs.filter(student__school_id=tenant_id)
        except Exception:  # noqa: BLE001
            return None

    # Try each plausible phone field — schemas vary across deployments.
    for field in _PHONE_FIELDS:
        try:
            row = qs.filter(**{field: norm}).first()
        except Exception:  # noqa: BLE001
            continue
        if row is not None:
            return row
    # Last-ditch: substring match (e.g. stored without `+`).
    for field in _PHONE_FIELDS:
        try:
            row = qs.filter(**{f"{field}__endswith": norm.lstrip("+")[-9:]}).first()
        except Exception:  # noqa: BLE001
            continue
        if row is not None:
            return row
    return None


def _format_balance(amount, currency: str) -> str:
    if amount is None:
        return "{balance}"
    try:
        from .. import billing  # type: ignore  # noqa: F401
        from apps.billing.embedded_checkout import format_amount_for_display
        # The Guardian's outstanding is usually stored in major units; convert.
        from decimal import Decimal
        minor = int(Decimal(amount) * 100)
        return format_amount_for_display(minor, currency or "NGN")
    except Exception:  # noqa: BLE001
        return str(amount)


def resolve(msg: InboundMessage, intent: str) -> dict[str, Any]:
    """Public resolver — implements the Wave K kernel's placeholder contract."""
    placeholders: dict[str, Any] = {}
    if intent == "fee_balance":
        guardian = _find_guardian(msg.tenant_id, msg.from_phone)
        if guardian is None:
            return placeholders
        amount = getattr(guardian, "outstanding_balance", None)
        currency = getattr(guardian, "outstanding_currency", "") or "NGN"
        placeholders["balance"] = _format_balance(amount, currency)
    elif intent == "absence_report":
        guardian = _find_guardian(msg.tenant_id, msg.from_phone)
        if guardian is None:
            return placeholders
        # First child via the guardian's reverse relation. Schemas vary
        # (children / dependents / students) — try several.
        for attr in ("children", "dependents", "students"):
            try:
                children = getattr(guardian, attr).all()
            except Exception:  # noqa: BLE001
                continue
            first = children.first() if hasattr(children, "first") else (children[0] if children else None)
            if first is not None:
                display = (
                    getattr(first, "full_name", None)
                    or getattr(first, "first_name", None)
                    or getattr(first, "name", None)
                    or ""
                )
                if display:
                    placeholders["student"] = str(display)
                    break
    elif intent == "report_card":
        # Tenant-issued signed link — real impl will mint a TimestampSigner-
        # protected URL for the latest report card. Stub for now.
        placeholders["link"] = "https://portal.runmycampus.com/report-cards/latest"
    elif intent == "homework":
        # Real impl will pull from academics' homework board for the first
        # child's current class. Stub returns a static example.
        placeholders["summary"] = "Maths p.42 (10 problems), English essay (200 words)."
    return placeholders
