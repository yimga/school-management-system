"""
Marketplace split / subaccount flows (SFDP 1444).

Counsel-gated: requires ``SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN`` env (constant-time compare).
Without token, APIs return structured refusal — no silent split in production.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any


class PaymentSplitCounselRequiredError(ValueError):
    """Raised when split/subaccount path invoked without counsel approval token."""


@dataclass(frozen=True)
class SplitIntentResult:
    allowed: bool
    provider: str
    reason: str
    payload: dict[str, Any]


def counsel_token_configured() -> bool:
    return bool((os.environ.get("SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN") or "").strip())


def verify_counsel_token(submitted: str | None) -> bool:
    expected = (os.environ.get("SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN") or "").strip()
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted.strip())


def initiate_paystack_subaccount_split(
    *,
    school_id: int,
    amount_minor: int,
    subaccount_code: str,
    counsel_token: str | None = None,
) -> SplitIntentResult:
    if not verify_counsel_token(counsel_token):
        raise PaymentSplitCounselRequiredError(
            "Paystack subaccount split requires counsel-approved SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN."
        )
    return SplitIntentResult(
        allowed=True,
        provider="paystack",
        reason="counsel_approved_stub",
        payload={
            "school_id": school_id,
            "amount_minor": amount_minor,
            "subaccount_code": subaccount_code,
            "status": "stub_ready_for_live_api",
        },
    )


def initiate_flutterwave_marketplace_split(
    *,
    school_id: int,
    amount: str,
    subaccount_id: str,
    counsel_token: str | None = None,
) -> SplitIntentResult:
    if not verify_counsel_token(counsel_token):
        raise PaymentSplitCounselRequiredError(
            "Flutterwave split requires counsel-approved SFDP_PAYMENT_SPLIT_COUNSEL_TOKEN."
        )
    return SplitIntentResult(
        allowed=True,
        provider="flutterwave",
        reason="counsel_approved_stub",
        payload={
            "school_id": school_id,
            "amount": amount,
            "subaccount_id": subaccount_id,
            "status": "stub_ready_for_live_api",
        },
    )
