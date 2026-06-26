"""Flutterwave gateway for the apps.finance.gateways registry."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from apps.finance.gateway_http import http_get_json, http_post_json
from .base import BasePaymentGateway, GatewayResult
from . import registry


class FlutterwaveGateway(BasePaymentGateway):
    code = "flutterwave"

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
                message="Flutterwave gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )
        secret = str(self.config.get("secret_key") or "").strip()
        if secret and not self.config.get("stub_only"):
            email = str(kwargs.get("payer_email") or self.config.get("default_payer_email") or "").strip()
            redirect = str(kwargs.get("redirect_url") or self.config.get("redirect_url") or "").strip()
            if email and redirect:
                base = str(self.config.get("api_base") or "https://api.flutterwave.com/v3").rstrip("/")
                status, body = http_post_json(
                    f"{base}/payments",
                    {"Authorization": f"Bearer {secret}"},
                    {
                        "tx_ref": reference,
                        "amount": str(amount),
                        "currency": currency.upper(),
                        "redirect_url": redirect,
                        "customer": {
                            "email": email,
                            "phonenumber": payer_phone or "",
                        },
                        "customizations": {
                            "title": (description or "School fees")[:50],
                        },
                    },
                )
                if status and body and str(body.get("status") or "").lower() in {"success", "successful"}:
                    data = body.get("data") if isinstance(body.get("data"), dict) else {}
                    link = str(data.get("link") or "")
                    tx_ref = str(data.get("tx_ref") or reference)
                    return GatewayResult(
                        success=True,
                        transaction_id=tx_ref,
                        message="Flutterwave charge initialized (live HTTP).",
                        raw_response={
                            "status": "pending",
                            "provider": self.code,
                            "reference": tx_ref,
                            "payment_url": link,
                            "http_status": status,
                        },
                    )
                return GatewayResult(
                    success=False,
                    message="Flutterwave initialize failed.",
                    raw_response={"status": "http_error", "http_status": status, "body": body or {}},
                )
        return GatewayResult(
            success=True,
            transaction_id=f"flw_{reference}",
            message="Flutterwave charge initialised.",
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
        secret = str(self.config.get("secret_key") or "").strip()
        if secret and not self.config.get("stub_only"):
            base = str(self.config.get("api_base") or "https://api.flutterwave.com/v3").rstrip("/")
            ref = transaction_id.replace("flw_", "", 1)
            status, body = http_get_json(
                f"{base}/transactions/verify_by_reference?tx_ref={ref}",
                {"Authorization": f"Bearer {secret}"},
            )
            if status and body and str(body.get("status") or "").lower() in {"success", "successful"}:
                data = body.get("data") if isinstance(body.get("data"), dict) else {}
                pstatus = str(data.get("status") or "").strip().lower()
                is_success = pstatus in {"successful", "success", "completed", "paid"}
                return GatewayResult(
                    success=is_success,
                    transaction_id=ref,
                    message=f"Flutterwave status: {pstatus or 'unknown'}",
                    raw_response={"status": pstatus, "provider": self.code, "http_status": status},
                )
        status = (self.config.get("test_status") or "pending").strip().lower()
        is_success = status in {"success", "successful", "completed", "paid"}
        return GatewayResult(
            success=is_success,
            transaction_id=transaction_id,
            message=f"Flutterwave status: {status}",
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

        secret_hash = str(self.config.get("secret_hash") or self.config.get("webhook_secret") or "")
        if secret_hash and headers is not None:
            from apps.finance.webhooks.signature_verifiers import verify_flutterwave

            ok, reason = verify_flutterwave(
                headers,
                raw_body if raw_body is not None else b"",
                secret_hash,
            )
            if not ok:
                return GatewayResult(
                    success=False,
                    transaction_id=None,
                    message=f"Flutterwave webhook signature failed: {reason}",
                    raw_response={"signature_failed": True, "reason": reason},
                )

        event = str(payload.get("event") or "").strip()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        status = str((data or {}).get("status") or "").strip().lower()
        tx_id = str(
            (data or {}).get("tx_ref") or (data or {}).get("flw_ref") or (data or {}).get("id") or ""
        ).strip()
        if not tx_id:
            return None
        success = event in {"charge.completed", "transfer.completed"} or status in {
            "successful",
            "success",
            "completed",
            "paid",
        }
        return GatewayResult(
            success=success,
            transaction_id=tx_id,
            message=f"Flutterwave webhook parsed ({event or status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("flutterwave", FlutterwaveGateway)
