"""Stripe gateway for the apps.finance.gateways registry.

Distinct from ``apps.billing.processors.StripeConnectProcessor`` (which handles
platform-billing webhooks for the marketplace tier). This class handles the
school-tenant payment collection path: card payment intents per tenant.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .base import BasePaymentGateway, GatewayResult
from . import registry


class StripeGateway(BasePaymentGateway):
    code = "stripe"

    REQUIRED_CONFIG_KEYS = ("secret_key",)

    def _missing_config(self) -> list[str]:
        return [k for k in self.REQUIRED_CONFIG_KEYS if not self.config.get(k)]

    def initiate(
        self,
        amount: Decimal,
        currency: str,
        reference: str,
        payer_phone: Optional[str] = None,
        description: Optional[str] = None,
        platform_fee: Optional[Decimal] = None,
        **kwargs,
    ) -> GatewayResult:
        missing = self._missing_config()
        if missing:
            return GatewayResult(
                success=False,
                message="Stripe gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        school = kwargs.get("school")
        connect_account_id = ""
        connect_charges_enabled = False
        if school is not None:
            try:
                from apps.schools.stripe_connect_settings import get_stripe_connect_payload

                sc = get_stripe_connect_payload(school)
                connect_account_id = str(sc.get("account_id") or "").strip()
                connect_charges_enabled = bool(sc.get("charges_enabled"))
            except (ImportError, AttributeError, TypeError):
                connect_account_id = ""
        return GatewayResult(
            success=True,
            transaction_id=f"stripe_{reference}",
            message="Stripe payment intent ready (client must confirm).",
            raw_response={
                "status": "requires_confirmation",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
                "description": description or "",
                "platform_fee": str(platform_fee or Decimal("0")),
                "stripe_connect_account_id": connect_account_id,
                "stripe_connect_charges_enabled": connect_charges_enabled,
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        status = (self.config.get("test_status") or "pending").strip().lower()
        is_success = status in {"succeeded", "paid", "completed"}
        return GatewayResult(
            success=is_success,
            transaction_id=transaction_id,
            message=f"Stripe status: {status}",
            raw_response={"status": status, "provider": self.code, "transaction_id": transaction_id},
        )

    def parse_webhook(
        self,
        payload: dict,
        headers: Optional[dict] = None,
        raw_body: Optional[bytes] = None,
    ) -> Optional[GatewayResult]:
        if not isinstance(payload, dict) or not payload:
            return None
        event_type = str(payload.get("type") or "").strip()
        if not event_type.startswith("payment_intent.") and not event_type.startswith("charge."):
            return None

        webhook_secret = str(self.config.get("webhook_secret") or "")
        if webhook_secret and headers is not None:
            from apps.finance.webhooks.signature_verifiers import verify_stripe

            ok, reason = verify_stripe(
                headers,
                raw_body if raw_body is not None else b"",
                webhook_secret,
                tolerance_seconds=int(self.config.get("signature_tolerance_seconds") or 300),
            )
            if not ok:
                return GatewayResult(
                    success=False,
                    transaction_id=None,
                    message=f"Stripe webhook signature failed: {reason}",
                    raw_response={"signature_failed": True, "reason": reason},
                )

        data_obj = ((payload.get("data") or {}).get("object")) if isinstance(payload.get("data"), dict) else {}
        if not isinstance(data_obj, dict):
            data_obj = {}
        tx_id = str(data_obj.get("id") or "").strip()
        status = str(data_obj.get("status") or "").strip().lower()
        success = event_type == "payment_intent.succeeded" or status in {"succeeded", "paid"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id or None,
            message=f"Stripe webhook parsed ({event_type or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("stripe", StripeGateway)
