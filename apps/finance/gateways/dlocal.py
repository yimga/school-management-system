"""dLocal cross-border aggregator gateway."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .base import BasePaymentGateway, GatewayResult
from . import registry


class DlocalGateway(BasePaymentGateway):
    code = "dlocal"
    REQUIRED_CONFIG_KEYS = ("api_key", "secret_key")

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
                message="dLocal gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        return GatewayResult(
            success=True,
            transaction_id=f"dlocal_{reference}",
            message="dLocal payment initialised.",
            raw_response={
                "status": "pending",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        status = (self.config.get("test_status") or "pending").strip().lower()
        return GatewayResult(
            success=status in {"paid", "success", "completed"},
            transaction_id=transaction_id,
            message=f"dLocal status: {status}",
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
        tx_id = str(payload.get("id") or payload.get("payment_id") or "").strip()
        if not tx_id:
            return None
        status = str(payload.get("status") or "").strip().lower()
        success = status in {"paid", "success", "completed", "approved"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"dLocal webhook ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("dlocal", DlocalGateway)
