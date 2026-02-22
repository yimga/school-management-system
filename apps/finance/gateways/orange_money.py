"""Orange Money gateway (Phase 3). Config-driven adapter with webhook parsing."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import uuid4

from .base import BasePaymentGateway, GatewayResult

from . import registry  # noqa: F401


class OrangeMoneyGateway(BasePaymentGateway):
    code = "orange_money"

    REQUIRED_CONFIG_KEYS = ("client_id", "client_secret", "merchant_key")

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
                message="Orange Money gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )

        tx_id = f"orange_{reference or uuid4().hex[:16]}"
        return GatewayResult(
            success=True,
            transaction_id=tx_id,
            message="Orange Money collection request initiated.",
            raw_response={
                "status": "pending",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
                "payer_phone": payer_phone,
                "description": description or "",
                "platform_fee": str(platform_fee or Decimal("0")),
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        status = (self.config.get("test_status") or "pending").strip().lower()
        is_success = status in {"success", "completed", "paid"}
        return GatewayResult(
            success=is_success,
            transaction_id=transaction_id,
            message=f"Orange Money status: {status}",
            raw_response={"status": status, "provider": self.code, "transaction_id": transaction_id},
        )

    def parse_webhook(self, payload: dict, headers: Optional[dict] = None) -> Optional[GatewayResult]:
        if not isinstance(payload, dict) or not payload:
            return None

        provider = str(payload.get("provider") or "").strip().lower()
        if provider and provider not in {"orange", "orange_money", self.code}:
            return None

        status = str(payload.get("status") or payload.get("state") or payload.get("result") or "").strip().lower()
        tx_id = str(
            payload.get("transaction_id")
            or payload.get("reference")
            or payload.get("external_reference")
            or ""
        ).strip()
        if not tx_id:
            return None

        success = status in {"success", "successful", "completed", "paid"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Orange webhook parsed ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("orange_money", OrangeMoneyGateway)
