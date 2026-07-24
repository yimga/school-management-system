"""Outbound gateway collection — the collect-side counterpart to the inbound
webhook rail (:func:`apps.finance.views_payments.payment_provider_webhook`).

Resolves a school's configured gateway for a payment method and starts a
collection (an MTN MoMo request-to-pay / M-Pesa STK push / a redirect PSP order)
against an invoice's outstanding balance. This is the piece the platform never
had: the *dormant-but-real* gateways in ``apps/finance/gateways/`` had zero
callers, so a parent could never trigger a mobile-money collection. This module
is that missing call site.

Two hard safety properties — read before wiring anything:

* **FAIL-CLOSED + INERT.** Gated by ``settings.RMC_GATEWAY_COLLECTION_ENABLED``
  (default ``False`` via ``getattr`` — no settings.py edit needed to stay off).
  When on, a school with no gateway credentials gets ``success=False`` /
  ``not_configured`` from the gateway itself and NO charge is attempted. The
  concrete gateways already fail closed (see ``mtn_momo.py`` etc.).
* **SETTLEMENT IS WEBHOOK-ONLY.** This module NEVER writes a ``Payment`` or a
  ledger row. Money is recorded only when the provider's *signed* webhook
  arrives and ``record_provider_payment`` posts it. The collection reference
  carries the invoice id so that webhook can match the right invoice. This is
  deliberately NOT the fake-success ``payment_processors.py`` path.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.conf import settings

from apps.finance.gateways.base import GatewayResult
from apps.finance.gateways.registry import get_gateway

logger = logging.getLogger(__name__)

# Collection references are ``rmcinv-<invoice_id>-<nonce>`` so the invoice id
# round-trips through the PSP (as externalId/metadata) and back in the webhook,
# where ``payment_provider_webhook`` matches ``Invoice.objects.get(id=...)``.
_REFERENCE_PREFIX = "rmcinv"


def build_collection_reference(invoice_id) -> str:
    """Mint a collection reference that carries ``invoice_id``."""
    return f"{_REFERENCE_PREFIX}-{invoice_id}-{uuid4().hex[:12]}"


def invoice_id_from_reference(reference) -> int | None:
    """Recover the invoice id a collection reference was minted for, or ``None``."""
    if not reference:
        return None
    parts = str(reference).split("-")
    if len(parts) >= 3 and parts[0] == _REFERENCE_PREFIX and parts[1].isdigit():
        return int(parts[1])
    return None


def _resolve_invoice_currency(invoice) -> str:
    """Best-effort 3-letter currency for the collection: invoice currency ->
    linked compliance profile -> school -> ``USD``. Mirrors how ``Payment`` and
    the invoice itself resolve currency, without importing them."""
    currency = getattr(invoice, "currency", None)
    code = (getattr(currency, "code", "") or "").strip() if currency is not None else ""
    if not code:
        profile = getattr(invoice, "profile", None)
        code = (getattr(profile, "currency_code", "") or "").strip()
    if not code:
        school = getattr(invoice, "school", None)
        code = (getattr(school, "currency_code", "") or "").strip()
    return code.upper() or "USD"


def _outstanding_amount(invoice) -> Decimal:
    amount = getattr(invoice, "computed_balance", None)
    if amount is None:
        amount = getattr(invoice, "total_amount", None)
    try:
        return Decimal(str(amount if amount is not None else "0"))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def initiate_invoice_collection(
    *,
    invoice,
    method_code: str,
    payer_phone: str | None = None,
    description: str | None = None,
    policy: dict | None = None,
) -> GatewayResult:
    """Start a gateway collection against ``invoice``'s outstanding balance.

    Returns the gateway's :class:`GatewayResult` unchanged. Never settles money:
    a ``success=True`` result means the collection was *requested* (e.g. the
    payer's phone will prompt); the ``Payment`` is posted only when the signed
    webhook confirms it. Every failure mode returns ``success=False`` with a
    machine-readable ``raw_response["status"]`` and posts nothing.
    """
    if not getattr(settings, "RMC_GATEWAY_COLLECTION_ENABLED", False):
        return GatewayResult(
            success=False,
            message="Online collection is not enabled for this deployment.",
            raw_response={"status": "collection_disabled"},
        )

    school = getattr(invoice, "school", None)
    if school is None:
        return GatewayResult(
            success=False,
            message="Invoice is not attached to a school.",
            raw_response={"status": "no_school"},
        )

    amount = _outstanding_amount(invoice)
    if amount <= 0:
        return GatewayResult(
            success=False,
            message="Invoice has no outstanding balance to collect.",
            raw_response={"status": "nothing_due"},
        )

    gateway = get_gateway(school, method_code, policy=policy)
    if gateway is None:
        return GatewayResult(
            success=False,
            message=f"No payment gateway is configured for method '{method_code}'.",
            raw_response={"status": "no_gateway", "method": method_code},
        )

    reference = build_collection_reference(getattr(invoice, "pk", None))
    currency = _resolve_invoice_currency(invoice)
    result = gateway.initiate(
        amount=amount,
        currency=currency,
        reference=reference,
        payer_phone=payer_phone,
        description=description or f"Invoice {getattr(invoice, 'pk', '')}",
    )
    logger.info(
        "Gateway collection initiated invoice=%s method=%s currency=%s success=%s",
        getattr(invoice, "pk", None),
        method_code,
        currency,
        bool(getattr(result, "success", False)),
    )
    # NEVER post a Payment here — settlement is webhook-only.
    return result
