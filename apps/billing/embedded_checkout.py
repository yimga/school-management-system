"""Wave I (v3.95.0 — 2026-05-26) — Embedded Checkout for parent fee payments.

This is the **Shopify-of-school-payments** primitive: a tenant can embed a
drop-in checkout widget on their own marketing/portal site that creates a
payment-intent against *that tenant's* PSP credentials (Stripe Connect /
Paystack / Flutterwave / MTN MoMo / Razorpay).

The platform never holds the tenant's funds — every checkout session is
created against the tenant's connected merchant account; settlement flows
direct merchant. The platform takes a configurable per-transaction fee
(default 0% during pilot; tenant-configurable upper bound).

This module is the **session creation kernel**. It does not call any PSP API;
it produces a `CheckoutSessionRequest` and hands off to the existing PSP
adapter registry (`apps.billing.psp_adapter_registry`) which routes to the
correct vendor adapter behind feature flags.

Boundary: NO direct PSP SDK imports here. All vendor calls route through
`psp_adapter_registry`. NO `services.ai_gateway` imports (the AI gateway is
the gateway-pattern source of truth; this module is parallel infrastructure).
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable


logger = logging.getLogger(__name__)


_PAYMENT_PURPOSES: tuple[str, ...] = (
    "tuition_fee",
    "transport_fee",
    "boarding_fee",
    "exam_fee",
    "uniform",
    "books",
    "lunch",
    "field_trip",
    "extracurricular",
    "donation",
    "other",
)


@dataclass(frozen=True)
class CheckoutLineItem:
    """A single line on a parent's invoice."""

    sku: str
    description: str
    amount_minor: int  # in smallest currency unit (e.g. cents, kobo)
    currency: str
    quantity: int = 1


@dataclass(frozen=True)
class CheckoutSessionRequest:
    """The kernel's input. Tenant identifier + parent + line items."""

    tenant_id: str
    parent_email: str
    parent_phone: str
    line_items: tuple[CheckoutLineItem, ...]
    purpose: str = "tuition_fee"
    student_reference: str = ""  # tenant-internal student ID
    locale: str = "en"
    success_url: str = ""
    cancel_url: str = ""
    preferred_processor: str = ""  # "stripe" / "paystack" / "flutterwave" / "" = auto


@dataclass
class CheckoutSessionResult:
    """The kernel's output. Either a hosted URL or an error reason."""

    ok: bool
    session_id: str = ""
    hosted_url: str = ""
    processor: str = ""
    total_minor: int = 0
    currency: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _normalize_currency(code: str) -> str:
    out = (code or "").strip().upper()
    if len(out) != 3 or not out.isascii() or not out.isalpha():
        return ""
    return out


def validate_request(req: CheckoutSessionRequest) -> str:
    """Pure validator — returns empty string on success, error message on failure."""
    if not req.tenant_id:
        return "tenant_id is required"
    if not req.parent_email and not req.parent_phone:
        return "parent contact (email or phone) is required"
    if not req.line_items:
        return "at least one line item is required"
    if req.purpose not in _PAYMENT_PURPOSES:
        return f"purpose '{req.purpose}' is not in the allowed set"

    currencies = {_normalize_currency(li.currency) for li in req.line_items}
    if "" in currencies:
        return "every line item must have a 3-letter ISO currency"
    if len(currencies) > 1:
        return "all line items must share the same currency"

    for li in req.line_items:
        if li.amount_minor <= 0:
            return f"line item '{li.sku}' has non-positive amount"
        if li.quantity <= 0:
            return f"line item '{li.sku}' has non-positive quantity"

    return ""


def total_minor(req: CheckoutSessionRequest) -> int:
    return sum(li.amount_minor * li.quantity for li in req.line_items)


def session_currency(req: CheckoutSessionRequest) -> str:
    if not req.line_items:
        return ""
    return _normalize_currency(req.line_items[0].currency)


# ---------------------------------------------------------------------------
# Processor selection
# ---------------------------------------------------------------------------

_CURRENCY_TO_PREFERRED_PROCESSORS: dict[str, tuple[str, ...]] = {
    # Africa
    "NGN": ("paystack", "flutterwave", "stripe"),
    "GHS": ("paystack", "flutterwave"),
    "KES": ("flutterwave", "mtn_momo"),
    "UGX": ("flutterwave", "mtn_momo"),
    "TZS": ("flutterwave", "mtn_momo"),
    "RWF": ("flutterwave", "mtn_momo"),
    "ZAR": ("stripe", "flutterwave"),
    "XAF": ("flutterwave", "mtn_momo", "orange_money"),
    "XOF": ("flutterwave", "orange_money", "mtn_momo"),
    "EGP": ("stripe", "flutterwave"),
    "MAD": ("stripe",),
    # India / South Asia
    "INR": ("razorpay", "stripe"),
    "PKR": ("stripe",),
    "BDT": ("stripe",),
    "LKR": ("stripe",),
    # SE Asia
    "PHP": ("stripe",),
    "IDR": ("stripe",),
    "MYR": ("stripe",),
    "THB": ("stripe",),
    "VND": ("stripe",),
    # Americas / Europe / Oceania
    "USD": ("stripe",),
    "CAD": ("stripe",),
    "GBP": ("stripe",),
    "EUR": ("stripe",),
    "AUD": ("stripe",),
    "NZD": ("stripe",),
    "BRL": ("stripe",),
    "MXN": ("stripe",),
    "CLP": ("stripe",),
    "COP": ("stripe",),
    "ARS": ("stripe",),
    "AED": ("stripe",),
    "SAR": ("stripe",),
}


def candidate_processors(req: CheckoutSessionRequest) -> tuple[str, ...]:
    """Return processors that can handle this request's currency, ordered by
    locality preference (most-local first)."""
    if req.preferred_processor:
        return (req.preferred_processor,)
    cur = session_currency(req)
    return _CURRENCY_TO_PREFERRED_PROCESSORS.get(cur, ("stripe",))


# ---------------------------------------------------------------------------
# Session kernel
# ---------------------------------------------------------------------------

def _generate_session_id(req: CheckoutSessionRequest) -> str:
    """Stable-prefix session id for audit + tenant log correlation."""
    nonce = secrets.token_hex(8)
    seed = f"{req.tenant_id}:{req.parent_phone or req.parent_email}:{nonce}"
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"rmc_ck_{h}"


def create_session(
    req: CheckoutSessionRequest,
    *,
    psp_dispatcher: Callable[[str, CheckoutSessionRequest, str, int], dict[str, Any]] | None = None,
) -> CheckoutSessionResult:
    """Create a checkout session — pure kernel + dispatcher callback.

    The ``psp_dispatcher`` callable is the seam where the real PSP adapter
    routes the session through to Stripe / Paystack / etc. Signature:

        psp_dispatcher(processor, request, session_id, total_minor) -> dict

    Must return a dict with keys ``ok`` (bool), ``hosted_url`` (str), and
    optionally ``error`` (str). When ``psp_dispatcher`` is None (default
    used by tests + the in-repo verifier), the session is returned in
    "ready-to-dispatch" form with a placeholder ``hosted_url`` so callers
    can verify request-shape without going live.
    """
    err = validate_request(req)
    if err:
        return CheckoutSessionResult(ok=False, error=err)

    candidates = candidate_processors(req)
    if not candidates:
        return CheckoutSessionResult(
            ok=False, error=f"no processor available for currency {session_currency(req)}",
        )

    session_id = _generate_session_id(req)
    total = total_minor(req)
    currency = session_currency(req)

    # Try each candidate processor in order. First success wins.
    last_error = ""
    for processor in candidates:
        if psp_dispatcher is None:
            # No dispatcher provided — return ready-to-dispatch shape.
            return CheckoutSessionResult(
                ok=True,
                session_id=session_id,
                hosted_url=f"https://checkout.runmycampus.com/{session_id}",
                processor=processor,
                total_minor=total,
                currency=currency,
                metadata={"dispatched": False, "purpose": req.purpose},
            )
        try:
            outcome = psp_dispatcher(processor, req, session_id, total) or {}
        except Exception as exc:  # noqa: BLE001
            last_error = f"{processor} dispatcher raised: {exc}"
            logger.warning(
                "embedded_checkout dispatcher failed processor=%s err=%s",
                processor, exc,
            )
            continue
        if outcome.get("ok"):
            return CheckoutSessionResult(
                ok=True,
                session_id=session_id,
                hosted_url=str(outcome.get("hosted_url") or ""),
                processor=processor,
                total_minor=total,
                currency=currency,
                metadata={"dispatched": True, "purpose": req.purpose,
                          **(outcome.get("metadata") or {})},
            )
        last_error = str(outcome.get("error") or f"{processor} returned not-ok")

    return CheckoutSessionResult(
        ok=False,
        error=last_error or "no processor succeeded",
        total_minor=total,
        currency=currency,
    )


# ---------------------------------------------------------------------------
# Public introspection
# ---------------------------------------------------------------------------

def allowed_purposes() -> tuple[str, ...]:
    return _PAYMENT_PURPOSES


def format_amount_for_display(amount_minor: int, currency: str) -> str:
    """Best-effort major-unit display (cents → dollars, kobo → naira, etc.).

    Currencies with 0 decimals (JPY, KRW, VND, XAF, XOF) are detected by a
    small allowlist; everything else assumes 2 decimals.
    """
    zero_decimal = {"JPY", "KRW", "VND", "XAF", "XOF", "UGX", "RWF", "BIF"}
    cur = _normalize_currency(currency)
    if cur in zero_decimal:
        return f"{amount_minor:,} {cur}"
    major = Decimal(amount_minor) / Decimal(100)
    return f"{major:,.2f} {cur}"
