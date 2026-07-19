"""Safaricom M-Pesa Daraja STK Push gateway (metric #26 East Africa rail).

Fail-closed: missing consumer key/secret/shortcode/passkey refuses success.
Live HTTP path uses sandbox ``sandbox.safaricom.co.ke`` when credentials exist
and ``stub_only`` is not set. EXTERNAL: Daraja partner certification + live charge.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from apps.finance.gateway_http import http_get_json, http_post_json
from .base import BasePaymentGateway, GatewayResult
from . import registry  # noqa: F401


class MpesaDarajaGateway(BasePaymentGateway):
    code = "mpesa_daraja"

    REQUIRED_CONFIG_KEYS = (
        "consumer_key",
        "consumer_secret",
        "shortcode",
        "passkey",
    )

    def _missing_config(self) -> list[str]:
        return [k for k in self.REQUIRED_CONFIG_KEYS if not self.config.get(k)]

    def _token(self, base: str) -> tuple[int, dict]:
        key = str(self.config.get("consumer_key") or "").strip()
        secret = str(self.config.get("consumer_secret") or "").strip()
        basic = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
        return http_get_json(
            f"{base}/oauth/v1/generate?grant_type=client_credentials",
            {"Authorization": f"Basic {basic}"},
        )

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
                message="M-Pesa Daraja gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        if currency.upper() not in {"KES", "TZS", "UGX"}:
            return GatewayResult(
                success=False,
                message=f"M-Pesa Daraja does not support currency {currency}.",
                raw_response={"status": "unsupported_currency", "currency": currency},
            )
        if not self.config.get("stub_only") and not payer_phone:
            return GatewayResult(
                success=False,
                message=(
                    "M-Pesa Daraja is live-configured but no payer phone was supplied; "
                    "refusing to report success for an STK Push that was never sent."
                ),
                raw_response={"status": "missing_payer_phone"},
            )

        if not self.config.get("stub_only") and payer_phone:
            base = str(
                self.config.get("api_base_url")
                or "https://sandbox.safaricom.co.ke"
            ).rstrip("/")
            status, token_body = self._token(base)
            access = str((token_body or {}).get("access_token") or "").strip()
            if status not in {200, 201} or not access:
                return GatewayResult(
                    success=False,
                    message="M-Pesa OAuth token request failed.",
                    raw_response={
                        "status": "oauth_error",
                        "http_status": status,
                        "body": token_body or {},
                    },
                )
            shortcode = str(self.config.get("shortcode") or "").strip()
            passkey = str(self.config.get("passkey") or "").strip()
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            password = base64.b64encode(
                f"{shortcode}{passkey}{timestamp}".encode("utf-8")
            ).decode("ascii")
            callback = str(self.config.get("callback_url") or "").strip()
            phone = payer_phone.lstrip("+")
            amount_int = int(amount.quantize(Decimal("1")))
            stk_status, stk_body = http_post_json(
                f"{base}/mpesa/stkpush/v1/processrequest",
                {"Authorization": f"Bearer {access}"},
                {
                    "BusinessShortCode": shortcode,
                    "Password": password,
                    "Timestamp": timestamp,
                    "TransactionType": "CustomerPayBillOnline",
                    "Amount": amount_int,
                    "PartyA": phone,
                    "PartyB": shortcode,
                    "PhoneNumber": phone,
                    "CallBackURL": callback or f"{base}/mpesa/callback",
                    "AccountReference": (reference or "fees")[:12],
                    "TransactionDesc": (description or "School fees")[:13],
                },
            )
            if stk_status in {200, 201} and str(
                (stk_body or {}).get("ResponseCode") or ""
            ) in {"0", "00"}:
                checkout = str(
                    (stk_body or {}).get("CheckoutRequestID")
                    or (stk_body or {}).get("MerchantRequestID")
                    or reference
                )
                return GatewayResult(
                    success=True,
                    transaction_id=checkout,
                    message="M-Pesa STK Push initiated (live HTTP).",
                    raw_response={
                        "status": "pending",
                        "provider": self.code,
                        "http_status": stk_status,
                        "body": stk_body or {},
                    },
                )
            return GatewayResult(
                success=False,
                message="M-Pesa STK Push failed.",
                raw_response={
                    "status": "http_error",
                    "http_status": stk_status,
                    "body": stk_body or {},
                },
            )

        tx_id = f"mpesa_{reference or uuid4().hex[:16]}"
        return GatewayResult(
            success=True,
            transaction_id=tx_id,
            message="M-Pesa STK Push initiated (stub).",
            raw_response={
                "status": "pending",
                "provider": self.code,
                "reference": reference,
                "amount": str(amount),
                "currency": currency,
                "payer_phone": payer_phone,
            },
        )

    def check_status(self, transaction_id: str) -> GatewayResult:
        status = (self.config.get("test_status") or "pending").strip().lower()
        is_success = status in {"success", "completed", "paid"}
        return GatewayResult(
            success=is_success,
            transaction_id=transaction_id,
            message=f"M-Pesa status: {status}",
            raw_response={"status": status, "provider": self.code},
        )

    def parse_webhook(
        self, payload: dict, headers: Optional[dict] = None, raw_body: Optional[bytes] = None
    ) -> Optional[GatewayResult]:
        if not isinstance(payload, dict) or not payload:
            return None
        body = payload.get("Body") if isinstance(payload.get("Body"), dict) else payload
        callback = body.get("stkCallback") if isinstance(body, dict) else None
        if not isinstance(callback, dict):
            callback = body if isinstance(body, dict) else {}
        result_code = str(
            callback.get("ResultCode")
            or payload.get("ResultCode")
            or payload.get("status")
            or ""
        ).strip()
        tx_id = str(
            callback.get("CheckoutRequestID")
            or payload.get("CheckoutRequestID")
            or payload.get("transaction_id")
            or ""
        ).strip()
        if not tx_id:
            return None
        success = result_code in {"0", "00", "success", "completed"}
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"M-Pesa webhook parsed (ResultCode={result_code or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("mpesa_daraja", MpesaDarajaGateway)
registry.register_gateway("mpesa", MpesaDarajaGateway)
