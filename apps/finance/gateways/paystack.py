"""Paystack gateway for the apps.finance.gateways registry."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from .base import BasePaymentGateway, GatewayResult
from . import registry


class PaystackGateway(BasePaymentGateway):
    code = "paystack"

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
                message="Paystack gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        return GatewayResult(
            success=True,
            transaction_id=f"paystack_{reference}",
            message="Paystack transaction initialised.",
            raw_response={
                "status": "pending",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
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
            message=f"Paystack status: {status}",
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

        secret = str(self.config.get("secret_key") or "")
        if secret and headers is not None:
            from apps.finance.webhooks.signature_verifiers import verify_paystack

            ok, reason = verify_paystack(
                headers,
                raw_body if raw_body is not None else b"",
                secret,
            )
            if not ok:
                return GatewayResult(
                    success=False,
                    transaction_id=None,
                    message=f"Paystack webhook signature failed: {reason}",
                    raw_response={"signature_failed": True, "reason": reason},
                )

        event = str(payload.get("event") or "").strip()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        status = str((data or {}).get("status") or payload.get("status") or "").strip().lower()
        tx_id = str((data or {}).get("reference") or (data or {}).get("id") or payload.get("id") or "").strip()
        if not tx_id:
            return None
        success = event == "charge.success" or status in {"success", "successful", "completed", "paid"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Paystack webhook parsed ({event or status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("paystack", PaystackGateway)
