"""Disabled future scope: platform collection/split of tenant school fees.

RunMyCampus currently provides tenant-owned gateway adapters only. It does not
collect, hold, split, transfer, or settle school-fee funds. These callable names
remain as compatibility seams, but they refuse unconditionally; an environment
variable must never turn the SaaS operator into a payment facilitator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class PaymentSplitCounselRequiredError(ValueError):
    """Compatibility error for the disabled collect-on-behalf feature."""


@dataclass(frozen=True)
class SplitIntentResult:
    allowed: bool
    provider: str
    reason: str
    payload: dict[str, Any]


def counsel_token_configured() -> bool:
    """Always false: collection on behalf cannot be enabled by configuration."""
    return False


def verify_counsel_token(submitted: str | None) -> bool:
    """Always false until a separately designed future product replaces this stub."""
    return False


def _raise_collection_on_behalf_disabled() -> None:
    raise PaymentSplitCounselRequiredError(
        "RunMyCampus collection, custody, and split settlement of tenant funds is "
        "disabled future scope. Configure the tenant's own PSP instead."
    )


def initiate_paystack_subaccount_split(
    *, school_id: int, amount_minor: int, subaccount_code: str,
    counsel_token: str | None = None,
) -> SplitIntentResult:
    _raise_collection_on_behalf_disabled()


def initiate_flutterwave_marketplace_split(
    *, school_id: int, amount: str, subaccount_id: str,
    counsel_token: str | None = None,
) -> SplitIntentResult:
    _raise_collection_on_behalf_disabled()
