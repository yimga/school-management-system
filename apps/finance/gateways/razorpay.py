"""Razorpay gateway (India / UPI + cards).

Live-configured tenants (key_id + key_secret, stub_only off) POST to the
Razorpay Orders API. Missing keys → not_configured. stub_only → deliberate
local success. Never fabricate success when live keys are present.
"""

from __future__ import annotations

import base64
from decimal import Decimal
from typing import Optional

from apps.finance.gateway_http import http_get_json, http_post_json

from . import registry
from .base import BasePaymentGateway, GatewayResult


class RazorpayGateway(BasePaymentGateway):
    code = "razorpay"
    REQUIRED_CONFIG_KEYS = ("key_id", "key_secret")

    def _missing_config(self) -> list[str]:
        return [k for k in self.REQUIRED_CONFIG_KEYS if not self.config.get(k)]

    def _auth_header(self) -> str:
        key_id = str(self.config.get("key_id") or "").strip()
        key_secret = str(self.config.get("key_secret") or "").strip()
        token = base64.b64encode(f"{key_id}:{key_secret}".encode("utf-8")).decode(
            "ascii"
        )
        return f"Basic {token}"

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
        key_id = str(self.config.get("key_id") or "").strip()
        key_secret = str(self.config.get("key_secret") or "").strip()
        if key_id and key_secret and not self.config.get("stub_only"):
            base = str(
                self.config.get("api_base") or "https://api.razorpay.com/v1"
            ).rstrip("/")
            # Razorpay amounts are minor units (paise for INR).
            minor = int((amount * Decimal("100")).quantize(Decimal("1")))
            if minor <= 0:
                return GatewayResult(
                    success=False,
                    message="Razorpay amount must be positive.",
                    raw_response={"status": "invalid_amount"},
                )
            status, body = http_post_json(
                f"{base}/orders",
                {
                    "Authorization": self._auth_header(),
                    "Content-Type": "application/json",
                },
                {
                    "amount": minor,
                    "currency": (currency or "INR").upper(),
                    "receipt": str(reference)[:40],
                    "notes": {
                        "description": description or "",
                        "payer_phone": payer_phone or "",
                    },
                },
            )
            if status and body and body.get("id"):
                order_id = str(body.get("id") or "")
                return GatewayResult(
                    success=True,
                    transaction_id=order_id,
                    message="Razorpay order created (live HTTP).",
                    raw_response={
                        "status": str(body.get("status") or "created"),
                        "provider": self.code,
                        "reference": reference,
                        "order_id": order_id,
                        "amount": body.get("amount"),
                        "currency": body.get("currency"),
                        "http_status": status,
                    },
                )
            return GatewayResult(
                success=False,
                message="Razorpay order create failed.",
                raw_response={
                    "status": "http_error",
                    "http_status": status,
                    "body": body or {},
                },
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
        key_id = str(self.config.get("key_id") or "").strip()
        key_secret = str(self.config.get("key_secret") or "").strip()
        if key_id and key_secret and not self.config.get("stub_only"):
            base = str(
                self.config.get("api_base") or "https://api.razorpay.com/v1"
            ).rstrip("/")
            order_id = transaction_id.replace("razorpay_", "", 1)
            status, body = http_get_json(
                f"{base}/orders/{order_id}",
                {"Authorization": self._auth_header()},
            )
            if status and body:
                pstatus = str(body.get("status") or "").strip().lower()
                return GatewayResult(
                    success=pstatus in {"paid", "captured", "attempted"},
                    transaction_id=str(body.get("id") or transaction_id),
                    message=f"Razorpay status: {pstatus or 'unknown'}",
                    raw_response={
                        "status": pstatus,
                        "provider": self.code,
                        "http_status": status,
                    },
                )
            return GatewayResult(
                success=False,
                message="Razorpay status probe failed.",
                raw_response={"status": "http_error", "http_status": status},
            )
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
            entity = (
                payload.get("payment", {})
                if isinstance(payload.get("payment"), dict)
                else payload
            )
        tx_id = str(entity.get("id") or payload.get("id") or "").strip()
        if not tx_id:
            return None
        status = str(entity.get("status") or payload.get("event") or "").strip().lower()
        success = status in {
            "captured",
            "authorized",
            "payment.captured",
            "paid",
            "success",
        }
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Razorpay webhook ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("razorpay", RazorpayGateway)
