"""Mercado Pago gateway (LATAM / Pix).

Live-configured tenants (access_token, stub_only off) POST checkout
preferences. Missing token → not_configured. stub_only → deliberate local
success. Never fabricate success when a live token is present.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from apps.finance.gateway_http import http_get_json, http_post_json

from . import registry
from .base import BasePaymentGateway, GatewayResult


class MercadoPagoGateway(BasePaymentGateway):
    code = "mercado_pago"
    REQUIRED_CONFIG_KEYS = ("access_token",)

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
                message="Mercado Pago gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        token = str(self.config.get("access_token") or "").strip()
        if token and not self.config.get("stub_only"):
            base = str(
                self.config.get("api_base") or "https://api.mercadopago.com"
            ).rstrip("/")
            title = (description or f"School payment {reference}").strip()[:120]
            payer_email = str(
                kwargs.get("payer_email")
                or self.config.get("default_payer_email")
                or ""
            ).strip()
            payload: dict = {
                "external_reference": str(reference),
                "items": [
                    {
                        "title": title,
                        "quantity": 1,
                        "unit_price": float(amount),  # money-float-allow: gateway-input-format
                        "currency_id": (currency or "BRL").upper(),
                    }
                ],
            }
            if payer_email:
                payload["payer"] = {"email": payer_email}
            if payer_phone:
                payload.setdefault("metadata", {})["payer_phone"] = payer_phone
            status, body = http_post_json(
                f"{base}/checkout/preferences",
                {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                payload,
            )
            if status and body and (body.get("id") or body.get("init_point")):
                pref_id = str(body.get("id") or reference)
                return GatewayResult(
                    success=True,
                    transaction_id=pref_id,
                    message="Mercado Pago preference created (live HTTP).",
                    raw_response={
                        "status": "pending",
                        "provider": self.code,
                        "reference": reference,
                        "preference_id": pref_id,
                        "init_point": str(body.get("init_point") or ""),
                        "sandbox_init_point": str(
                            body.get("sandbox_init_point") or ""
                        ),
                        "http_status": status,
                    },
                )
            return GatewayResult(
                success=False,
                message="Mercado Pago preference create failed.",
                raw_response={
                    "status": "http_error",
                    "http_status": status,
                    "body": body or {},
                },
            )
        return GatewayResult(
            success=True,
            transaction_id=f"mp_{reference}",
            message="Mercado Pago preference created.",
            raw_response={
                "status": "pending",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        token = str(self.config.get("access_token") or "").strip()
        if token and not self.config.get("stub_only"):
            base = str(
                self.config.get("api_base") or "https://api.mercadopago.com"
            ).rstrip("/")
            # Preferences are not payment status; probe /v1/payments when id looks numeric.
            path_id = transaction_id.replace("mp_", "", 1)
            status, body = http_get_json(
                f"{base}/v1/payments/{path_id}",
                {"Authorization": f"Bearer {token}"},
            )
            if status and body:
                pstatus = str(body.get("status") or "").strip().lower()
                return GatewayResult(
                    success=pstatus in {"approved", "accredited", "authorized"},
                    transaction_id=str(body.get("id") or transaction_id),
                    message=f"Mercado Pago status: {pstatus or 'unknown'}",
                    raw_response={
                        "status": pstatus,
                        "provider": self.code,
                        "http_status": status,
                    },
                )
            return GatewayResult(
                success=False,
                message="Mercado Pago status probe failed.",
                raw_response={"status": "http_error", "http_status": status},
            )
        status = (self.config.get("test_status") or "pending").strip().lower()
        return GatewayResult(
            success=status in {"approved", "accredited", "success", "paid"},
            transaction_id=transaction_id,
            message=f"Mercado Pago status: {status}",
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
        data = payload.get("data", {}) if isinstance(payload.get("data"), dict) else payload
        tx_id = str(data.get("id") or payload.get("id") or "").strip()
        if not tx_id:
            return None
        status = str(data.get("status") or payload.get("action") or "").strip().lower()
        success = status in {"approved", "accredited", "payment.created", "success"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Mercado Pago webhook ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("mercado_pago", MercadoPagoGateway)
