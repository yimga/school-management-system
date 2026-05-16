"""
Payment Service Provider (PSP) adapter registry.

Lane-2 scaffolding: external PSP contracting / certification is not code work,
but the *internal preparedness* is. This registry pins which PSPs the platform
can hand a tenant to today, which are in spec only, and what each adapter's
capability matrix is (cards, mobile money, bank transfer, payouts, refunds,
3DS, webhooks).

When commercial work begins, this is the operator-facing scoreboard that
prevents promising a PSP we don't actually integrate, and the regression test
fails if an `adapter_status="live"` row loses its model/route proof.

Add a row to ANNOUNCE intent. Flip status to `live` only after the integration
tests are green and the operator surface renders without 5xx.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PSPRow:
    """One Payment Service Provider candidate or integration."""

    psp_slug: str
    """Stable kebab-case key. Used in URL params + audit logs."""

    label: str
    """Display name (e.g., 'Stripe', 'Paystack', 'Flutterwave')."""

    region: str
    """Primary region: `global` | `africa` | `emea` | `apac` | `americas`."""

    adapter_status: str = "planned"
    """`live` | `in_progress` | `planned`. Drives the regression test."""

    capabilities: frozenset[str] = field(default_factory=frozenset)
    """Subset of {`cards`, `mobile_money`, `bank_transfer`, `payouts`, `refunds`, `3ds`, `webhooks`, `recurring`, `marketplace_split`}."""

    settlement_currencies: tuple[str, ...] = ()
    """ISO-4217 codes the adapter can settle into."""

    proof_model: str | None = None
    """`app_label.ModelName` of the connector model when live."""

    proof_route_name: str | None = None
    """URL name of the operator-facing connector page when live."""

    docs_url: str | None = None
    """Link to PSP's developer docs."""

    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["capabilities"] = sorted(self.capabilities)
        return d


PSP_REGISTER: tuple[PSPRow, ...] = (
    PSPRow(
        psp_slug="stripe",
        label="Stripe",
        region="global",
        adapter_status="in_progress",
        capabilities=frozenset({"cards", "bank_transfer", "refunds", "3ds", "webhooks", "recurring"}),
        settlement_currencies=("USD", "EUR", "GBP", "NGN"),
        docs_url="https://stripe.com/docs",
        notes="Stripe Checkout + Billing customer portal scaffolded in apps/siteconfig/views_billing_stripe.py.",
    ),
    PSPRow(
        psp_slug="paystack",
        label="Paystack",
        region="africa",
        adapter_status="planned",
        capabilities=frozenset({"cards", "bank_transfer", "mobile_money", "refunds", "webhooks"}),
        settlement_currencies=("NGN", "GHS", "ZAR", "KES"),
        docs_url="https://paystack.com/docs",
        notes="Priority PSP for NG/GH market entry. Mobile-money corridor is the differentiator.",
    ),
    PSPRow(
        psp_slug="flutterwave",
        label="Flutterwave",
        region="africa",
        adapter_status="planned",
        capabilities=frozenset({"cards", "bank_transfer", "mobile_money", "refunds", "webhooks", "payouts"}),
        settlement_currencies=("NGN", "GHS", "KES", "UGX", "ZAR", "USD"),
        docs_url="https://developer.flutterwave.com/",
        notes="Pan-African coverage incl. payouts. Pair with Paystack for redundancy.",
    ),
    PSPRow(
        psp_slug="mpesa-daraja",
        label="M-Pesa (Safaricom Daraja)",
        region="africa",
        adapter_status="planned",
        capabilities=frozenset({"mobile_money", "payouts", "webhooks"}),
        settlement_currencies=("KES",),
        docs_url="https://developer.safaricom.co.ke/",
        notes="Direct mobile-money rail for Kenya. STK Push for fee collection.",
    ),
    PSPRow(
        psp_slug="adyen",
        label="Adyen",
        region="emea",
        adapter_status="planned",
        capabilities=frozenset({"cards", "bank_transfer", "refunds", "3ds", "webhooks", "recurring", "marketplace_split"}),
        settlement_currencies=("EUR", "GBP", "USD"),
        docs_url="https://docs.adyen.com/",
        notes="For EMEA enterprise; marketplace split useful for multi-tenant settlements.",
    ),
    PSPRow(
        psp_slug="paypal",
        label="PayPal",
        region="global",
        adapter_status="planned",
        capabilities=frozenset({"cards", "refunds", "webhooks", "recurring"}),
        settlement_currencies=("USD", "EUR", "GBP"),
        docs_url="https://developer.paypal.com/",
        notes="Diaspora-to-school remittance use case.",
    ),
    PSPRow(
        psp_slug="razorpay",
        label="Razorpay",
        region="apac",
        adapter_status="planned",
        capabilities=frozenset({"cards", "bank_transfer", "refunds", "webhooks", "recurring"}),
        settlement_currencies=("INR",),
        docs_url="https://razorpay.com/docs/",
        notes="India market. UPI rail is the unique capability.",
    ),
)


def iter_psps() -> tuple[PSPRow, ...]:
    return PSP_REGISTER


def psp_slugs() -> frozenset[str]:
    return frozenset(p.psp_slug for p in PSP_REGISTER)


def get_psp(slug: str) -> PSPRow | None:
    for p in PSP_REGISTER:
        if p.psp_slug == slug:
            return p
    return None


def status_counts() -> dict[str, int]:
    out: dict[str, int] = {"live": 0, "in_progress": 0, "planned": 0}
    for p in PSP_REGISTER:
        out[p.adapter_status] = out.get(p.adapter_status, 0) + 1
    return out
