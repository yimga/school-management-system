"""Razorpay gateway (India / UPI + cards)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .base import BasePaymentGateway, GatewayResult
from . import registry


class RazorpayGateway(BasePaymentGateway):
    code = "razorpay"
    REQUIRED_CONFIG_KEYS = ("key_id", "key_secret")

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
                message="Razorpay gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        return GatewayResult(
            success=True,
            transaction_id=f"razorpay_{reference}",
            message="Razorpay order initialised.",
            raw_response={
                "status": "created",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        status = (self.config.get("test_status") or "pending").strip().lower()
        return GatewayResult(
            success=status in {"success", "captured", "paid"},
            transaction_id=transaction_id,
            message=f"Razorpay status: {status}",
            raw_response={"status": status, "provider": self.code},
        )

    def parse_webhook(
        self,
        payload: dict,
        headers: Optional[dict] = None,
        raw_body: Optional[bytes] = None,
    ) -> Optional[GatewayResult]:
        if not isinstance(payload, dict):
            return None
        entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
        if not isinstance(entity, dict):
            entity = payload.get("payment", {}) if isinstance(payload.get("payment"), dict) else payload
        tx_id = str(entity.get("id") or payload.get("id") or "").strip()
        if not tx_id:
            return None
        status = str(entity.get("status") or payload.get("event") or "").strip().lower()
        success = status in {"captured", "authorized", "payment.captured", "paid", "success"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Razorpay webhook ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("razorpay", RazorpayGateway)
