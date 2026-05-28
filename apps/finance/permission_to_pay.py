"""
Permission-to-pay workflow — micro-friction service.

Bundles event permission + payment authorization into a single workflow.
Guardian approval is required for amounts above the per-tenant threshold.
Payment authorization routes through apps.finance.payment_rail_adapter; no
live PSP call happens here.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
from decimal import Decimal

from apps.finance.payment_rail_adapter import (
    PaymentIntent,
    PaymentResult,
    registry as payment_registry,
)


logger = logging.getLogger(__name__)


class PermissionToPayError(RuntimeError):
    pass


@dataclass(frozen=True)
class GuardianApproval:
    guardian_id: str
    approved_at_iso: str
    method: str  # "portal" | "sms" | "email" | "in_person"


@dataclass
class PermissionToPayRequest:
    request_id: str
    tenant_id_hash: str
    student_id_hash: str
    event_code: str
    amount: Decimal
    currency: str
    requires_guardian_approval: bool
    guardian_approval: GuardianApproval | None = None
    payment_result: PaymentResult | None = None
    state: str = "pending"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def open_request(
    *,
    tenant_id: str,
    student_id: str,
    event_code: str,
    amount: Decimal,
    currency: str,
    guardian_threshold: Decimal,
) -> PermissionToPayRequest:
    if amount <= 0:
        raise PermissionToPayError("amount must be positive")
    if not isinstance(amount, Decimal) or not isinstance(guardian_threshold, Decimal):
        raise PermissionToPayError("amounts must be Decimal")
    req = PermissionToPayRequest(
        request_id=str(uuid.uuid4()),
        tenant_id_hash=_hash(tenant_id),
        student_id_hash=_hash(student_id),
        event_code=event_code,
        amount=amount,
        currency=currency,
        requires_guardian_approval=amount >= guardian_threshold,
        state="awaiting_guardian" if amount >= guardian_threshold else "ready_to_pay",
    )
    logger.info(
        "permission_to_pay.open request=%s tenant=%s student=%s event=%s state=%s",
        req.request_id,
        req.tenant_id_hash,
        req.student_id_hash,
        event_code,
        req.state,
        extra={"scope": "permission_to_pay.open"},
    )
    return req


def record_guardian_approval(
    request: PermissionToPayRequest,
    *,
    guardian_id: str,
    approved_at_iso: str,
    method: str,
) -> PermissionToPayRequest:
    if not request.requires_guardian_approval:
        raise PermissionToPayError("guardian approval not required for this request")
    if method not in {"portal", "sms", "email", "in_person"}:
        raise PermissionToPayError(f"invalid approval method {method!r}")
    request.guardian_approval = GuardianApproval(
        guardian_id=_hash(guardian_id),
        approved_at_iso=approved_at_iso,
        method=method,
    )
    request.state = "ready_to_pay"
    return request


def authorize_payment(
    request: PermissionToPayRequest,
    *,
    tenant_id_raw_for_intent: str,
    preferred_rails: tuple[str, ...] = (),
) -> PermissionToPayRequest:
    if request.requires_guardian_approval and request.guardian_approval is None:
        raise PermissionToPayError("guardian approval missing")
    if request.state != "ready_to_pay":
        raise PermissionToPayError(f"cannot pay from state {request.state!r}")
    intent = PaymentIntent(
        tenant_id=tenant_id_raw_for_intent,
        currency=request.currency,
        amount=request.amount,
        idempotency_key=request.request_id,
        description=f"event:{request.event_code}",
    )
    result = payment_registry().authorize(intent, preferred=preferred_rails)
    request.payment_result = result
    request.state = "paid" if result.success else "failed"
    logger.info(
        "permission_to_pay.pay request=%s rail=%s state=%s",
        request.request_id,
        result.rail_id,
        request.state,
        extra={"scope": "permission_to_pay.pay"},
    )
    return request


__all__ = [
    "GuardianApproval",
    "PermissionToPayError",
    "PermissionToPayRequest",
    "authorize_payment",
    "open_request",
    "record_guardian_approval",
]
