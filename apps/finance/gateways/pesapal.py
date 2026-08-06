"""Pesapal gateway (East Africa)."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .base import BasePaymentGateway, GatewayResult
from . import registry


class PesapalGateway(BasePaymentGateway):
    code = "pesapal"
    REQUIRED_CONFIG_KEYS = ("consumer_key", "consumer_secret")

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
                message="Pesapal gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        if self.config.get("stub_only"):
            # Deliberate local/test stub mode (pinned by the fail-closed contract).
            return GatewayResult(
                success=True,
                transaction_id=f"pesapal_{reference}",
                message="Pesapal payment request created (stub).",
                raw_response={
                    "status": "pending",
                    "provider": self.code,
                    "reference": reference,
                    "amount": str(amount),
                    "currency": currency,
                    "stub_only": True,
                },
            )
        # Live-configured, but NO live HTTP initiation is implemented for Pesapal
        # yet. FAIL CLOSED rather than fabricate success for a charge never sent.
        return GatewayResult(
            success=False,
            transaction_id=None,
            message=(
                "Pesapal live collection is not implemented yet — use a supported "
                "rail, or set stub_only for local testing."
            ),
            raw_response={
                "status": "initiation_not_implemented",
                "provider": self.code,
                "reference": reference,
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        status = (self.config.get("test_status") or "pending").strip().lower()
        return GatewayResult(
            success=status in {"completed", "success", "paid"},
            transaction_id=transaction_id,
            message=f"Pesapal status: {status}",
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
        tx_id = str(
            payload.get("order_tracking_id")
            or payload.get("OrderTrackingId")
            or payload.get("reference")
            or ""
        ).strip()
        if not tx_id:
            return None
        status = str(
            payload.get("payment_status_description")
            or payload.get("status")
            or ""
        ).strip().lower()
        success = status in {"completed", "success", "paid"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Pesapal IPN ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("pesapal", PesapalGateway)
