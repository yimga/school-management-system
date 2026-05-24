"""
Unified PSP webhook event shape (SFDP 1430).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


@dataclass(frozen=True)
class CanonicalPaymentWebhookEvent:
    provider: str
    event_id: str
    school_id: Optional[int]
    invoice_id: Optional[int]
    amount_decimal: Decimal
    currency: str
    status: str
    raw_ref: str

    def is_success(self) -> bool:
        return self.status in {"success", "completed", "paid", "successful"}


def _decimal_amount(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def normalize_provider_payload(
    provider: str,
    payload: dict[str, Any],
    *,
    metadata: Optional[dict[str, Any]] = None,
) -> Optional[CanonicalPaymentWebhookEvent]:
    """Map provider-specific JSON to a canonical event; None when unparseable."""
    provider_slug = (provider or "").strip().lower()
    meta = metadata if isinstance(metadata, dict) else {}
    if not isinstance(payload, dict):
        return None

    if provider_slug == "paystack":
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        event_id = str(data.get("reference") or data.get("id") or payload.get("id") or "").strip()
        status = str(data.get("status") or payload.get("event") or "").strip().lower()
        amount = _decimal_amount(data.get("amount", 0)) / Decimal("100")
        currency = str(data.get("currency") or "NGN").upper()[:3]
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else meta
    elif provider_slug in {"flutterwave", "flw"}:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        event_id = str(data.get("tx_ref") or data.get("id") or "").strip()
        status = str(data.get("status") or payload.get("event") or "").strip().lower()
        amount = _decimal_amount(data.get("amount") or data.get("charged_amount"))
        currency = str(data.get("currency") or "XAF").upper()[:3]
        meta = data.get("meta") if isinstance(data.get("meta"), dict) else meta
    elif provider_slug in {"mtn_momo", "mtn-momo", "mtn"}:
        event_id = str(payload.get("externalId") or payload.get("referenceId") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        amount = _decimal_amount(payload.get("amount"))
        currency = str(payload.get("currency") or "XAF").upper()[:3]
    elif provider_slug in {"orange_money", "orange-money", "orange"}:
        event_id = str(payload.get("transaction_id") or payload.get("order_id") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        amount = _decimal_amount(payload.get("amount"))
        currency = str(payload.get("currency") or "XAF").upper()[:3]
    elif provider_slug == "stripe":
        obj = payload.get("data", {}).get("object", {}) if payload.get("object") is None else {}
        if not isinstance(obj, dict):
            obj = payload.get("object") if isinstance(payload.get("object"), dict) else {}
        event_id = str(obj.get("id") or payload.get("id") or "").strip()
        status = str(obj.get("status") or payload.get("type") or "").strip().lower()
        amount = _decimal_amount(obj.get("amount_received") or obj.get("amount", 0)) / Decimal("100")
        currency = str(obj.get("currency") or "usd").upper()[:3]
        meta = obj.get("metadata") if isinstance(obj.get("metadata"), dict) else meta
    elif provider_slug == "razorpay":
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        if not isinstance(entity, dict):
            entity = payload
        event_id = str(entity.get("id") or "").strip()
        status = str(entity.get("status") or payload.get("event") or "").strip().lower()
        amount = _decimal_amount(entity.get("amount", 0)) / Decimal("100")
        currency = str(entity.get("currency") or "INR").upper()[:3]
        notes = entity.get("notes") if isinstance(entity.get("notes"), dict) else {}
        meta = notes or meta
    elif provider_slug == "pesapal":
        event_id = str(
            payload.get("order_tracking_id") or payload.get("OrderTrackingId") or ""
        ).strip()
        status = str(payload.get("payment_status_description") or payload.get("status") or "").lower()
        amount = _decimal_amount(payload.get("amount") or 0)
        currency = str(payload.get("currency") or "KES").upper()[:3]
    elif provider_slug in {"mercado_pago", "mercadopago", "mp"}:
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else payload
        event_id = str(data.get("id") or "").strip()
        status = str(data.get("status") or payload.get("action") or "").lower()
        amount = _decimal_amount(data.get("transaction_amount") or data.get("amount") or 0)
        currency = str(data.get("currency_id") or data.get("currency") or "USD").upper()[:3]
    elif provider_slug == "dlocal":
        event_id = str(payload.get("id") or payload.get("payment_id") or "").strip()
        status = str(payload.get("status") or "").lower()
        amount = _decimal_amount(payload.get("amount") or 0)
        currency = str(payload.get("currency") or "USD").upper()[:3]
    else:
        event_id = str(payload.get("reference") or payload.get("id") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        amount = _decimal_amount(payload.get("amount"))
        currency = str(payload.get("currency") or "USD").upper()[:3]

    if not event_id:
        return None

    school_id = meta.get("school_id")
    invoice_id = meta.get("invoice_id")
    try:
        school_id = int(school_id) if school_id is not None else None
    except (TypeError, ValueError):
        school_id = None
    try:
        invoice_id = int(invoice_id) if invoice_id is not None else None
    except (TypeError, ValueError):
        invoice_id = None

    if status in {"charge.success", "successful", "succeeded", "captured", "approved", "accredited"}:
        status = "success"

    return CanonicalPaymentWebhookEvent(
        provider=provider_slug,
        event_id=event_id,
        school_id=school_id,
        invoice_id=invoice_id,
        amount_decimal=amount,
        currency=currency,
        status=status,
        raw_ref=event_id,
    )
