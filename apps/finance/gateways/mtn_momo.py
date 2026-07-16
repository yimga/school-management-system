"""MTN Mobile Money gateway (Phase 3). Config-driven adapter with webhook parsing."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional
from uuid import uuid4

from apps.finance.gateway_http import http_get_json, http_post_json
from .base import BasePaymentGateway, GatewayResult
from . import registry  # noqa: F401


class MTNMoMoGateway(BasePaymentGateway):
    code = "mtn_momo"

    REQUIRED_CONFIG_KEYS = ("subscription_key", "api_user", "api_key")

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
                message="MTN MoMo gateway not configured.",
                raw_response={"status": "not_configured", "missing": missing},
            )

        api_user = str(self.config.get("api_user") or "").strip()
        api_key = str(self.config.get("api_key") or "").strip()
        subscription_key = str(self.config.get("subscription_key") or "").strip()
        if not self.config.get("stub_only") and not payer_phone:
            # FAIL CLOSED. _missing_config() above already returned for unconfigured
            # tenants, so reaching here with stub mode off means this gateway is
            # live-configured and the caller intends a real collection. Without a
            # payer phone no request-to-pay is sent; the condition below would then
            # be False and control would fall through to the success return, handing
            # back a fabricated mtn_<ref> transaction_id for money never requested.
            return GatewayResult(
                success=False,
                message=(
                    "MTN MoMo is live-configured but no payer phone was supplied; "
                    "refusing to report success for a collection that was never sent."
                ),
                raw_response={"status": "missing_payer_phone"},
            )
        if (
            api_user
            and api_key
            and subscription_key
            and not self.config.get("stub_only")
            and payer_phone
        ):
            ref_id = reference if len(reference) >= 32 else uuid4().hex
            zero_decimal = {"XAF", "XOF", "UGX", "RWF", "BIF"}
            amount_major = amount if currency.upper() in zero_decimal else (amount).quantize(Decimal("0.01"))
            base = str(
                self.config.get("api_base_url")
                or self.config.get("api_base")
                or "https://sandbox.momodeveloper.mtn.com"
            ).rstrip("/")
            target_env = str(self.config.get("target_environment") or "sandbox")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "X-Reference-Id": ref_id,
                "X-Target-Environment": target_env,
                "Ocp-Apim-Subscription-Key": subscription_key,
            }
            status, body = http_post_json(
                f"{base}/collection/v1_0/requesttopay",
                headers,
                {
                    "amount": str(amount_major),
                    "currency": currency.upper(),
                    "externalId": reference,
                    "payer": {
                        "partyIdType": "MSISDN",
                        "partyId": payer_phone.lstrip("+"),
                    },
                    "payerMessage": (description or "School fees")[:160],
                    "payeeNote": reference[:160],
                },
            )
            if status in {200, 201, 202}:
                return GatewayResult(
                    success=True,
                    transaction_id=ref_id,
                    message="MTN MoMo request-to-pay initiated (live HTTP).",
                    raw_response={
                        "status": "pending",
                        "provider": self.code,
                        "reference": reference,
                        "polling_url": f"{base}/collection/v1_0/requesttopay/{ref_id}",
                        "http_status": status,
                        "body": body or {},
                    },
                )
            return GatewayResult(
                success=False,
                message="MTN MoMo request-to-pay failed.",
                raw_response={"status": "http_error", "http_status": status, "body": body or {}},
            )

        tx_id = f"mtn_{reference or uuid4().hex[:16]}"
        return GatewayResult(
            success=True,
            transaction_id=tx_id,
            message="MTN MoMo collection request initiated.",
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
        api_key = str(self.config.get("api_key") or "").strip()
        subscription_key = str(self.config.get("subscription_key") or "").strip()
        if api_key and subscription_key and not self.config.get("stub_only"):
            ref = transaction_id.replace("mtn_", "", 1)
            base = str(
                self.config.get("api_base_url")
                or self.config.get("api_base")
                or "https://sandbox.momodeveloper.mtn.com"
            ).rstrip("/")
            target_env = str(self.config.get("target_environment") or "sandbox")
            status, body = http_get_json(
                f"{base}/collection/v1_0/requesttopay/{ref}",
                {
                    "Authorization": f"Bearer {api_key}",
                    "X-Target-Environment": target_env,
                    "Ocp-Apim-Subscription-Key": subscription_key,
                },
            )
            if status and body:
                pstatus = str(body.get("status") or "").strip().upper()
                is_success = pstatus == "SUCCESSFUL"
                return GatewayResult(
                    success=is_success,
                    transaction_id=ref,
                    message=f"MTN MoMo status: {pstatus or 'unknown'}",
                    raw_response={
                        "status": pstatus.lower(),
                        "provider": self.code,
                        "http_status": status,
                    },
                )
        status = (self.config.get("test_status") or "pending").strip().lower()
        is_success = status in {"success", "completed", "paid"}
        return GatewayResult(
            success=is_success,
            transaction_id=transaction_id,
            message=f"MTN MoMo status: {status}",
            raw_response={
                "status": status,
                "provider": self.code,
                "transaction_id": transaction_id,
            },
        )

    def parse_webhook(
        self, payload: dict, headers: Optional[dict] = None, raw_body: Optional[bytes] = None
    ) -> Optional[GatewayResult]:
        if not isinstance(payload, dict) or not payload:
            return None

        provider = str(payload.get("provider") or "").strip().lower()
        if provider and provider not in {"mtn", "mtn_momo", self.code}:
            return None

        signature_cfg = self.config.get("webhook_signature") or {}
        if signature_cfg.get("required") and headers is not None:
            from apps.finance.webhooks.signature_verifiers import verify_aggregator_hmac

            ok, reason = verify_aggregator_hmac(
                headers,
                raw_body if raw_body is not None else b"",
                str(signature_cfg.get("secret") or self.config.get("api_key") or ""),
                header_name=str(signature_cfg.get("header_name") or ""),
                algorithm=str(signature_cfg.get("algorithm") or "sha256"),
                timestamp_header=signature_cfg.get("timestamp_header") or None,
                tolerance_seconds=int(signature_cfg.get("tolerance_seconds") or 300),
                body_template=str(signature_cfg.get("body_template") or "{body}"),
            )
            if not ok:
                return GatewayResult(
                    success=False,
                    transaction_id=None,
                    message=f"MTN webhook signature failed: {reason}",
                    raw_response={"signature_failed": True, "reason": reason},
                )

        status = (
            str(
                payload.get("status")
                or payload.get("state")
                or payload.get("result")
                or ""
            )
            .strip()
            .lower()
        )
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
            message=f"MTN webhook parsed ({status or 'unknown'})",
            raw_response=payload,
        )


registry.register_gateway("mtn_momo", MTNMoMoGateway)
