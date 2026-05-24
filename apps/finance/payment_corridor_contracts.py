"""
PSP webhook + metadata contracts per pilot corridor (SFDP 1438–1440).

Single source for required metadata keys on initiate/webhook paths — tests lock drift.
"""

from __future__ import annotations

from typing import Final

# Paystack — NG/GH (minor units in webhook; metadata on initiate)
PAYSTACK_REQUIRED_METADATA_KEYS: Final[frozenset[str]] = frozenset({"invoice_id", "school_id"})
PAYSTACK_WEBHOOK_SUCCESS_EVENTS: Final[frozenset[str]] = frozenset(
    {"charge.success", "success", "successful"}
)

# Flutterwave — CM + multi-country
FLUTTERWAVE_REQUIRED_METADATA_KEYS: Final[frozenset[str]] = frozenset({"invoice_id", "school_id"})
FLUTTERWAVE_WEBHOOK_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset(
    {"successful", "success", "completed"}
)

# Stripe tuition webhooks (Engine 2 card path when school uses Stripe for fees)
STRIPE_TUITION_METADATA_KEYS: Final[frozenset[str]] = frozenset({"invoice_id", "school_id"})
STRIPE_TUITION_SUCCESS_STATUSES: Final[frozenset[str]] = frozenset(
    {"succeeded", "success", "paid", "payment_intent.succeeded"}
)

# Stripe Connect platform (Engine 1 — account lifecycle, not tuition ledger)
STRIPE_CONNECT_ACCOUNT_EVENTS: Final[frozenset[str]] = frozenset({"account.updated"})


def metadata_keys_complete(provider_slug: str, metadata: dict) -> bool:
    slug = (provider_slug or "").strip().lower()
    required = PAYSTACK_REQUIRED_METADATA_KEYS
    if slug in {"flutterwave", "flw"}:
        required = FLUTTERWAVE_REQUIRED_METADATA_KEYS
    elif slug == "stripe":
        required = STRIPE_TUITION_METADATA_KEYS
    if not isinstance(metadata, dict):
        return False
    return required <= {str(k) for k in metadata.keys()}
